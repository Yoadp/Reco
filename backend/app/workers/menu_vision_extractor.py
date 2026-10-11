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
  poetry run python -u -m app.workers.menu_vision_extractor --wolt-only   (stored slug → preview items)
  poetry run python -u -m app.workers.menu_vision_extractor --wolt-smart  (location search → best match with items)
"""

import asyncio
import argparse
import base64
import json
import math
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


# ─── Wolt smart search (location-first, no pre-stored slug needed) ────────────

WOLT_LISTING = "https://consumer-api.wolt.com/v1/pages/restaurants"
WOLT_BASE = "https://wolt.com/il/isr"

CITY_COORDS: dict[str, list[tuple[float, float]]] = {
    "תל אביב": [(32.0853, 34.7818), (32.0650, 34.7750), (32.1050, 34.7900)],
    "רמת גן":  [(32.0681, 34.8238)],
    "גבעתיים": [(32.0706, 34.8109)],
    "בני ברק": [(32.0833, 34.8340)],
    "פתח תקווה": [(32.0869, 34.8878)],
    "ראשון לציון": [(31.9642, 34.8007), (31.9800, 34.7900)],
    "חולון":   [(32.0107, 34.7795)],
    "בת ים":   [(32.0220, 34.7528)],
    "הרצליה":  [(32.1663, 34.8436), (32.1800, 34.8300)],
    "רעננה":   [(32.1838, 34.8705)],
    "כפר סבא": [(32.1754, 34.9073)],
    "הוד השרון": [(32.1525, 34.8955)],
    "נתניה":   [(32.3215, 34.8532), (32.3000, 34.8600)],
    "רחובות":  [(31.8928, 34.8113)],
    "נס ציונה": [(31.9309, 34.7978)],
    "מודיעין": [(31.8969, 35.0095)],
}
CITY_SLUG: dict[str, str] = {
    "תל אביב": "tel-aviv", "רמת גן": "ramat-gan", "גבעתיים": "givatayim",
    "בני ברק": "bnei-brak", "פתח תקווה": "petah-tikva", "ראשון לציון": "rishon-lezion",
    "חולון": "holon", "בת ים": "bat-yam", "הרצליה": "herzliya", "רעננה": "raanana",
    "כפר סבא": "kfar-saba", "הוד השרון": "hod-hasharon", "נתניה": "netanya",
    "רחובות": "rehovot", "נס ציונה": "nes-ziona", "מודיעין": "modiin",
}


_NOISE = {
    "restaurant", "rest", "bar", "cafe", "kitchen", "tlv",
    "מסעדת", "קפה", "בר", "מסעדה", "שף",
    # city names — shared by many restaurants in the same city
    "תל", "אביב", "גן", "רמת", "גבעתיים", "ברק", "בני", "פתח", "תקווה",
    "ראשון", "לציון", "חולון", "בת", "ים", "הרצליה", "רעננה",
    "כפר", "סבא", "הוד", "השרון", "נתניה", "רחובות", "נס", "ציונה", "מודיעין",
}


def _normalize_name(s: str) -> str:
    s = s.lower()
    # Remove apostrophes/gershayim WITHOUT splitting the surrounding word
    s = re.sub(r"[׳’'״]", "", s)
    # Remove remaining non-Hebrew/non-word chars
    s = re.sub(r"[^\w\sא-ת]", " ", s)
    return " ".join(t for t in s.split() if t not in _NOISE and len(t) > 1)


def _name_similarity(a: str, b: str) -> float:
    na, nb = set(_normalize_name(a).split()), set(_normalize_name(b).split())
    if not na or not nb:
        return 0.0
    return len(na & nb) / max(len(na), len(nb))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _fetch_city_venues(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    try:
        r = await client.get(WOLT_LISTING, params={"lat": lat, "lon": lon},
                             headers={"Accept": "application/json", "Accept-Language": "he",
                                      "User-Agent": "Mozilla/5.0"}, timeout=12.0)
        if r.status_code != 200:
            return []
        venues = []
        for section in r.json().get("sections", []):
            if section.get("template") != "venue-vertical-list":
                continue
            for item in section.get("items", []):
                v = item.get("venue")
                if isinstance(v, dict) and v.get("slug") and v.get("venue_preview_items"):
                    venues.append(v)
        return venues
    except Exception:
        return []


def _preview_to_items(preview: list[dict]) -> list[dict]:
    return [
        {
            "name": pi.get("name", ""),
            "price_ils": int(pi["price"] / 100) if isinstance(pi.get("price"), (int, float)) and pi["price"] > 0 else None,
            "category": "אחר",
            "description": None,
        }
        for pi in preview if pi.get("name")
    ]


async def run_wolt_smart(
    slug_filter: str | None = None,
    redo: bool = False,
    limit: int | None = None,
):
    """
    For every place, fetch the Wolt listing near its coordinates and pick the
    closest venue (within 400m) with the best name similarity that has
    venue_preview_items. Saves menu items and upserts the Wolt DataSource.
    """
    async with AsyncSessionLocal() as db:
        all_places = list((await db.execute(
            select(Place).where(Place.lat.isnot(None), Place.lng.isnot(None))
        )).scalars().all())
        # Places already with wolt menus (skip unless --redo)
        if not redo:
            done_ids = set((await db.execute(
                select(MenuItem.place_id).where(MenuItem.source == "wolt").distinct()
            )).scalars().all())
        else:
            done_ids = set()
        # Existing wolt DataSource slugs
        wolt_rows = (await db.execute(
            select(DataSource).where(DataSource.source_type == "wolt")
        )).scalars().all()
        existing_wolt: dict[int, DataSource] = {r.place_id: r for r in wolt_rows}

    if slug_filter:
        all_places = [p for p in all_places if p.slug == slug_filter]
    targets = [p for p in all_places if p.id not in done_ids]
    if limit:
        targets = targets[:limit]

    _log(f"Wolt smart search — {len(targets)} places to process…")

    # Pre-fetch venues per city (multi-point for better coverage)
    cities_needed = {p.city for p in targets if p.city in CITY_COORDS}
    city_venues: dict[str, list[dict]] = {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for city in cities_needed:
            seen_slugs: set[str] = set()
            all_venues: list[dict] = []
            for lat, lon in CITY_COORDS[city]:
                batch = await _fetch_city_venues(client, lat, lon)
                for v in batch:
                    if v["slug"] not in seen_slugs:
                        seen_slugs.add(v["slug"])
                        all_venues.append(v)
                await asyncio.sleep(0.3)
            city_venues[city] = all_venues
            _log(f"  {city}: {len(all_venues)} Wolt venues with preview items")
            await asyncio.sleep(0.3)

        counts = {"wolt": 0, "failed": 0, "no_city": 0}

        for i, place in enumerate(targets, 1):
            city = place.city or ""
            venues = city_venues.get(city, [])
            if not venues:
                counts["no_city"] += 1
                continue

            best_venue = None
            best_score = 0.0

            for v in venues:
                loc = v.get("location", [])
                if len(loc) == 2:
                    vlon, vlat = loc[0], loc[1]
                    dist = _haversine_m(place.lat, place.lng, vlat, vlon)
                    if dist > 350:
                        continue
                    dist_score = max(0.0, 1.0 - dist / 350)
                else:
                    dist_score = 0.0

                name_sim = _name_similarity(place.name, v.get("name", ""))
                if name_sim < 0.30:  # hard minimum — must share ≥30% name tokens
                    continue
                score = dist_score * 0.35 + name_sim * 0.65

                if score > best_score:
                    best_score = score
                    best_venue = v

            if not best_venue or best_score < 0.35:
                counts["failed"] += 1
                _log(f"  [{i}/{len(targets)}] ✗ {place.name} (no match, best={best_score:.2f})")
                continue

            items = _preview_to_items(best_venue.get("venue_preview_items", []))
            if not items:
                counts["failed"] += 1
                continue

            # Save menu items (replace AI placeholder + old Wolt with fresh Wolt data)
            async with AsyncSessionLocal() as db:
                await db.execute(delete(MenuItem).where(MenuItem.place_id == place.id).where(MenuItem.source.in_(["ai", "menu_vision", "wolt"])))
                for item in items[:25]:
                    price = item.get("price_ils")
                    db.add(MenuItem(
                        place_id=place.id,
                        name=item["name"][:299],
                        price_ils=int(price) if price and str(price).isdigit() else None,
                        category=item.get("category"),
                        description=item.get("description"),
                        source="wolt",
                    ))
                # Upsert Wolt DataSource if different slug
                slug = best_venue.get("slug", "")
                city_slug = CITY_SLUG.get(city, "tel-aviv")
                wolt_url = f"{WOLT_BASE}/{city_slug}/restaurant/{slug}"
                if place.id not in existing_wolt:
                    db.add(DataSource(
                        place_id=place.id,
                        source_type="wolt",
                        source_name="Wolt",
                        url=wolt_url,
                        confidence=min(best_score, 0.85),
                    ))
                await db.commit()

            counts["wolt"] += 1
            _log(f"  [{i}/{len(targets)}] ✓ {place.name} → {best_venue['name']} (score={best_score:.2f}): {', '.join(x['name'] for x in items[:3])}")

    _log(f"\n✓ Wolt smart done — menus: {counts['wolt']}, no match: {counts['failed']}, no city: {counts['no_city']}")


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
    parser.add_argument("--wolt-smart", action="store_true", help="Location-based Wolt search — finds best match with preview items")
    args = parser.parse_args()
    if args.wolt_smart:
        asyncio.run(run_wolt_smart(slug_filter=args.slug, redo=args.redo, limit=args.limit))
    else:
        asyncio.run(run(slug_filter=args.slug, redo=args.redo, limit=args.limit, no_wolt=args.no_wolt, wolt_only=args.wolt_only))
