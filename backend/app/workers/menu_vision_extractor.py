"""
Menu Extractor — 2-layer menu scraping:

Layer 1: Restaurant's own website (menu_link DataSource)
  - PDF → pdfminer.six → Groq text
  - Image → base64 → Groq vision
  - HTML → Playwright (shared browser, fast) → Groq text

Layer 2: Wolt fallback (wolt DataSource)
  - Wolt public consumer API → structured JSON (instant, no browser)
  - Playwright fallback if API returns nothing

Performance: single Playwright browser reused across all restaurants.

MenuItem.source:
  'website' — scraped from restaurant's own site
  'wolt'    — from Wolt API
  'ai'      — legacy fabricated (deleted on success)

Usage:
  poetry run python -u -m app.workers.menu_vision_extractor
  poetry run python -u -m app.workers.menu_vision_extractor romano
  poetry run python -u -m app.workers.menu_vision_extractor --limit 50
  poetry run python -u -m app.workers.menu_vision_extractor --redo
"""

import asyncio
import argparse
import base64
import json
import re
import sys
import httpx
from bs4 import BeautifulSoup
from collections import defaultdict
from sqlalchemy import select, delete
from urllib.parse import urlparse

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource
from app.models.menu_item import MenuItem

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TEXT_MODEL = "qwen/qwen3.8-27b"
CALL_DELAY = 2.5

IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"

SKIP_DOMAINS = {
    "tabitisrael.co.il", "ontopo.co.il", "orderss.co.il",
    "10bis.co.il", "wolt.com", "mishloha.co.il",
    "getmood.io", "dmenu.co.il",
    "instagram.com", "facebook.com", "twitter.com",
    "beecommcloud.com", "wa.link",  # ordering platforms / whatsapp links
}

MENU_PROMPT = """This is a Hebrew restaurant menu. Extract ALL dishes.

Return ONLY a JSON array, no markdown:
[{"name": "שם המנה", "price_ils": 89, "category": "עיקריות", "description": "תיאור"}]

- Hebrew names exactly as written
- price_ils: integer or null
- category: ראשונות/סלטים/מרקים/פיצות/פסטות/סושי/עיקריות/גריל/צדדיות/קינוחים/שתייה/אחר
- If no menu items found, return []"""

TEXT_PROMPT = """Extract menu items from this Hebrew restaurant menu text.

Return ONLY a JSON array, no markdown:
[{{"name": "שם המנה", "price_ils": 89, "category": "עיקריות", "description": "תיאור"}}]

- Only actual dish names, not headers or slogans
- price_ils: integer from ₪/ש"ח patterns, or null
- category: ראשונות/סלטים/מרקים/פיצות/פסטות/סושי/עיקריות/גריל/צדדיות/קינוחים/שתייה/אחר
- If no dishes with prices found, return []

Text:
{text}"""


# ─── Utilities ────────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")

def _should_skip(url: str) -> bool:
    d = _domain(url)
    return any(s in d for s in SKIP_DOMAINS)

def _parse_items(content: str) -> list[dict]:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content)
    s, e = content.find("["), content.rfind("]") + 1
    if s == -1 or e == 0:
        return []
    try:
        return [i for i in json.loads(content[s:e]) if isinstance(i, dict) and i.get("name")]
    except Exception:
        return []

def _log(msg: str):
    print(msg, flush=True)


# ─── Content fetching ─────────────────────────────────────────────────────────

async def _get_ct(url: str, client: httpx.AsyncClient) -> str:
    try:
        r = await client.head(url, timeout=6.0, follow_redirects=True)
        return r.headers.get("content-type", "").split(";")[0].strip().lower()
    except Exception:
        return ""

async def _fetch_pdf_text(url: str, client: httpx.AsyncClient) -> str:
    try:
        from pdfminer.high_level import extract_text
        from io import BytesIO
        r = await client.get(url, timeout=20.0, follow_redirects=True)
        if r.status_code != 200:
            return ""
        return (extract_text(BytesIO(r.content)) or "")[:4000]
    except Exception:
        return ""

async def _fetch_image_b64(url: str, client: httpx.AsyncClient) -> str | None:
    try:
        r = await client.get(url, timeout=15.0, follow_redirects=True)
        return base64.b64encode(r.content).decode() if r.status_code == 200 else None
    except Exception:
        return None

async def _fetch_playwright(url: str, browser) -> str:
    """Fetch a URL using a shared Playwright browser instance."""
    try:
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle", timeout=12000)
        await page.wait_for_timeout(1500)
        html = await page.content()
        await ctx.close()

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()
        for sel in [".menu", "#menu", "[class*=menu]", "[id*=menu]", "main", "article"]:
            c = soup.select_one(sel)
            if c:
                text = c.get_text(" ", strip=True)
                if len(text) > 100:
                    return text[:4000]
        return soup.get_text(" ", strip=True)[:4000]
    except Exception as e:
        _log(f"    Playwright error: {e}")
        return ""


# ─── Groq calls ───────────────────────────────────────────────────────────────

async def _groq_vision(b64: str, client: httpx.AsyncClient) -> list[dict]:
    for attempt in range(3):
        try:
            r = await client.post(GROQ_URL,
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={"model": GROQ_VISION_MODEL, "max_tokens": 500, "temperature": 0.1,
                      "messages": [{"role": "user", "content": [
                          {"type": "text", "text": MENU_PROMPT},
                          {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                      ]}]}, timeout=30.0)
            if r.status_code == 429:
                await asyncio.sleep(60 + attempt * 30); continue
            r.raise_for_status()
            return _parse_items(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            if attempt == 2: _log(f"    Vision error: {e}")
            await asyncio.sleep(3)
    return []

async def _groq_text(text: str, client: httpx.AsyncClient) -> list[dict]:
    for attempt in range(3):
        try:
            r = await client.post(GROQ_URL,
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={"model": GROQ_TEXT_MODEL, "max_tokens": 500, "temperature": 0.1,
                      "messages": [{"role": "user", "content": TEXT_PROMPT.format(text=text)}]},
                timeout=20.0)
            if r.status_code == 429:
                wait = 60 + attempt * 30
                _log(f"    ⏳ OTPM limit, waiting {wait}s (attempt {attempt+1}/3)")
                await asyncio.sleep(wait); continue
            r.raise_for_status()
            return _parse_items(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            if attempt == 2: _log(f"    Text API error: {e}")
            await asyncio.sleep(3)
    return []


# ─── Layer 1: restaurant website ─────────────────────────────────────────────

async def _layer1(url: str, browser, client: httpx.AsyncClient) -> list[dict]:
    if _should_skip(url):
        _log(f"    ⏭  Skip platform ({_domain(url)})")
        return []
    ct = await _get_ct(url, client)
    if ct in IMAGE_TYPES or any(url.lower().endswith(e) for e in [".jpg",".jpeg",".png",".webp"]):
        _log("    🖼  Image")
        b64 = await _fetch_image_b64(url, client)
        return await _groq_vision(b64, client) if b64 else []
    if ct == PDF_TYPE or url.lower().endswith(".pdf"):
        _log("    📄 PDF")
        text = await _fetch_pdf_text(url, client)
        return await _groq_text(text, client) if text else []
    _log("    🌐 HTML (Playwright)")
    text = await _fetch_playwright(url, browser)
    return await _groq_text(text, client) if text else []


# ─── Layer 2: Wolt ────────────────────────────────────────────────────────────

def _wolt_slug(url: str) -> str | None:
    m = re.search(r"/restaurant/([^/?#]+)", url)
    return m.group(1) if m else None

async def _wolt_api(slug: str, client: httpx.AsyncClient, lat: float = 32.0853, lon: float = 34.7818) -> list[dict]:
    """
    Find the venue by slug in the nearby listing and extract venue_preview_items.
    lat/lon default to Tel Aviv centre; caller should pass the place's own coordinates.
    """
    try:
        r = await client.get(
            "https://consumer-api.wolt.com/v1/pages/restaurants",
            params={"lat": lat, "lon": lon},
            headers={"Accept": "application/json", "Accept-Language": "he", "app-language": "he"},
            timeout=10.0)
        if r.status_code != 200:
            return []
        for section in r.json().get("sections", []):
            if section.get("template") != "venue-vertical-list":
                continue
            for item in section.get("items", []):
                venue = item.get("venue", {})
                if venue.get("slug") != slug:
                    continue
                preview = venue.get("venue_preview_items", [])
                if not preview:
                    return []
                return [
                    {
                        "name": pi.get("name", ""),
                        "price_ils": int(pi["price"] / 100) if isinstance(pi.get("price"), (int, float)) and pi["price"] > 0 else None,
                        "category": "אחר",
                        "description": None,
                    }
                    for pi in preview if pi.get("name")
                ]
        return []
    except Exception as e:
        _log(f"    Wolt API error: {e}")
        return []

async def _layer2(url: str, browser, client: httpx.AsyncClient, lat: float = 32.0853, lon: float = 34.7818) -> list[dict]:
    slug = _wolt_slug(url)
    if not slug:
        return []
    _log(f"    🔵 Wolt API ({slug})")
    items = await _wolt_api(slug, client, lat=lat, lon=lon)
    if not items:
        _log("    🔵 Wolt Playwright fallback")
        text = await _fetch_playwright(url, browser)
        items = await _groq_text(text, client) if text else []
    return items


# ─── DB save ──────────────────────────────────────────────────────────────────

async def _save(place_id, items: list[dict], source: str):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(MenuItem).where(MenuItem.place_id == place_id).where(MenuItem.source == "ai"))
        await db.execute(delete(MenuItem).where(MenuItem.place_id == place_id).where(MenuItem.source == "menu_vision"))
        for item in items[:25]:
            price = item.get("price_ils")
            db.add(MenuItem(
                place_id=place_id,
                name=item["name"][:299],
                price_ils=int(price) if price and str(price).isdigit() else None,
                category=item.get("category"),
                description=item.get("description"),
                source=source,
            ))
        await db.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────

async def run(
    slug_filter: str | None = None,
    redo: bool = False,
    limit: int | None = None,
    no_wolt: bool = False,
    wolt_only: bool = False,
):
    async with AsyncSessionLocal() as db:
        stmt = (select(Place, DataSource)
            .join(DataSource, DataSource.place_id == Place.id)
            .where(DataSource.source_type.in_(["menu_link", "wolt"])))
        if slug_filter:
            stmt = stmt.where(Place.slug == slug_filter)
        rows = (await db.execute(stmt)).all()

    # Group by place
    place_map: dict[str, dict] = defaultdict(lambda: {"place": None, "menu_link": None, "wolt": None})
    for place, ds in rows:
        e = place_map[str(place.id)]
        e["place"] = place
        if ds.source_type == "menu_link" and not e["menu_link"]:
            e["menu_link"] = ds
        elif ds.source_type == "wolt" and not e["wolt"]:
            e["wolt"] = ds

    if not redo:
        async with AsyncSessionLocal() as db:
            done = {str(r) for r in (await db.execute(
                select(MenuItem.place_id).where(MenuItem.source.in_(["website","wolt"])).distinct()
            )).scalars()}
        place_map = {k: v for k, v in place_map.items() if k not in done}

    entries = list(place_map.values())
    if no_wolt:
        entries = [e for e in entries if e["menu_link"] is not None]
    if wolt_only:
        entries = [e for e in entries if e["wolt"] is not None]
    if limit:
        entries = entries[:limit]

    _log(f"Processing {len(entries)} places{' (Wolt API only — no Groq)' if wolt_only else ' (1 shared browser)'}...")
    counts = {"website": 0, "wolt": 0, "failed": 0}

    if wolt_only:
        # Fast path: Wolt API only, no browser, no Groq
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"},
            follow_redirects=True,
        ) as client:
            for i, entry in enumerate(entries, 1):
                place = entry["place"]
                wolt_ds = entry["wolt"]
                _log(f"[{i}/{len(entries)}] {place.name}")
                slug = _wolt_slug(wolt_ds.url) if wolt_ds else None
                if not slug:
                    counts["failed"] += 1
                    continue
                lat = place.lat or 32.0853
                lon = place.lng or 34.7818
                items = await _wolt_api(slug, client, lat=lat, lon=lon)
                if items:
                    await _save(place.id, items, "wolt")
                    counts["wolt"] += 1
                    _log(f"  ✓ {len(items)} items: {', '.join(x['name'] for x in items[:3])}")
                else:
                    counts["failed"] += 1
                    _log(f"  ✗ Wolt API returned nothing for {slug}")
                await asyncio.sleep(0.5)
    else:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"},
                follow_redirects=True,
            ) as client:
                for i, entry in enumerate(entries, 1):
                    place = entry["place"]
                    menu_ds = entry["menu_link"]
                    wolt_ds = entry["wolt"]
                    _log(f"\n[{i}/{len(entries)}] {place.name}")

                    items: list[dict] = []
                    src = ""

                    if menu_ds and menu_ds.url:
                        _log(f"    Layer 1: {menu_ds.url[:70]}")
                        try:
                            items = await _layer1(menu_ds.url, browser, client)
                        except Exception as e:
                            _log(f"    Layer 1 error: {e}")
                        if items:
                            src = "website"

                    if not items and not no_wolt and wolt_ds and wolt_ds.url:
                        _log(f"    Layer 2: {wolt_ds.url[:70]}")
                        try:
                            lat = place.lat or 32.0853
                            lon = place.lng or 34.7818
                            items = await _layer2(wolt_ds.url, browser, client, lat=lat, lon=lon)
                        except Exception as e:
                            _log(f"    Layer 2 error: {e}")
                        if items:
                            src = "wolt"

                    if items:
                        await _save(place.id, items, src)
                        counts[src] += 1
                        _log(f"    ✓ {len(items)} items ({src}): {', '.join(x['name'] for x in items[:3])}")
                    else:
                        counts["failed"] += 1
                        _log(f"    ✗ no menu found")

                    await asyncio.sleep(CALL_DELAY)

            await browser.close()

    _log(f"\n✓ Done — website: {counts['website']}, wolt: {counts['wolt']}, failed: {counts['failed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", nargs="?")
    parser.add_argument("--redo", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-wolt", action="store_true", help="Skip Wolt layer 2 fallback")
    parser.add_argument("--wolt-only", action="store_true", help="Wolt API only — fast, no Groq, no browser")
    args = parser.parse_args()
    asyncio.run(run(slug_filter=args.slug, redo=args.redo, limit=args.limit, no_wolt=args.no_wolt, wolt_only=args.wolt_only))
