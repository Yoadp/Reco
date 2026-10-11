"""
Walla Food scraper — discovers restaurant reviews on food.walla.co.il.

Two modes:
  City mode (default): DDG site:food.walla.co.il {city} ביקורת → 16 searches,
    works best for Hebrew-named restaurants.
  Per-restaurant mode (--per-restaurant): DDG site:food.walla.co.il "{name}"
    for every place in the DB without a Walla source — best overall coverage.

Usage:
  poetry run python -m app.workers.walla_city_scraper                     # city mode, all cities
  poetry run python -m app.workers.walla_city_scraper "תל אביב"           # city mode, one city
  poetry run python -m app.workers.walla_city_scraper --per-restaurant    # per-restaurant mode
  poetry run python -m app.workers.walla_city_scraper --redo              # overwrite existing
"""

import asyncio
import argparse
import re
from urllib.parse import quote_plus, unquote
from bs4 import BeautifulSoup
import httpx

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

WALLA_CITIES = [
    "תל אביב", "רמת גן", "גבעתיים", "בני ברק", "פתח תקווה",
    "ראשון לציון", "חולון", "בת ים", "הרצליה", "רעננה",
    "כפר סבא", "הוד השרון", "נתניה", "רחובות", "נס ציונה", "מודיעין",
]


# ─── Name matching ─────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    s = re.sub(r"[^\w\s֐-׿]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _name_similarity(a: str, b: str) -> float:
    na, nb = set(_normalize(a).split()), set(_normalize(b).split())
    if not na or not nb:
        return 0.0
    return len(na & nb) / max(len(na), len(nb))


def _extract_restaurant_name(title: str) -> str:
    """Pull restaurant name from common Walla title patterns."""
    # "ביקורת: NAME" / "ביקורת | NAME" / "ביקורת - NAME" / "ביקורת – NAME"
    m = re.search(r"ביקורת\s*[:\|\-–]\s*(.+?)(?:\s*[-–\|]|$)", title)
    if m:
        return m.group(1).strip()
    # "NAME - ביקורת" / "NAME | ביקורת"
    m = re.search(r"^(.+?)\s*[-–\|]\s*ביקורת", title)
    if m:
        return m.group(1).strip()
    # "NAME | וואלה אוכל" — strip trailing site suffix
    m = re.search(r"^(.+?)\s*[\|–-]\s*(?:וואלה|food\.walla)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # First segment before any separator
    m = re.search(r"^(.+?)\s*[\|–-]", title)
    if m:
        return m.group(1).strip()
    return title.strip()


def _best_match(title: str, city_places: list) -> tuple:
    """Return (place, score) — tries both full title and extracted name."""
    candidates = list({_extract_restaurant_name(title), title})
    best_place, best_score = None, 0.0
    for name in candidates:
        for place in city_places:
            score = _name_similarity(place.name, name)
            if score > best_score:
                best_score = score
                best_place = place
    return best_place, best_score


# ─── DDG site search ───────────────────────────────────────────────────────────

async def _ddg_walla_urls(query_term: str, client: httpx.AsyncClient, max_results: int = 20) -> list[str]:
    """
    Search DuckDuckGo for `site:food.walla.co.il {query_term}` and return
    up to max_results Walla article URLs.
    """
    query = f'site:food.walla.co.il {query_term}'
    try:
        r = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "il-he"},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "he-IL,he;q=0.9"},
            timeout=15.0,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        urls = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            m = re.search(r"uddg=([^&]+)", href)
            url = unquote(m.group(1)) if m else href
            if "food.walla.co.il/item" in url and url not in urls:
                urls.append(url)
        return urls[:max_results]
    except Exception as e:
        print(f"  DDG error: {e}")
        return []


# ─── Article fetching ──────────────────────────────────────────────────────────

async def _fetch_article(url: str, browser) -> dict | None:
    """Fetch a Walla article page; return {title, excerpt} or None on failure."""
    try:
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        html = await page.content()
        await ctx.close()
    except Exception as e:
        print(f"  Playwright error: {e}")
        return None

    soup = BeautifulSoup(html, "lxml")

    # Title: prefer <h1>, fallback to <title>
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    if not title:
        t = soup.find("title")
        title = t.get_text(" ", strip=True) if t else ""

    # Excerpt: first substantial paragraph in article body
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    excerpt = ""
    for selector in ["article", ".article-body", ".post-content", ".entry-content", "main"]:
        container = soup.select_one(selector)
        if container:
            for p in container.find_all("p"):
                text = p.get_text(" ", strip=True)
                if len(text) > 80:
                    excerpt = text[:400] + ("..." if len(text) > 400 else "")
                    break
        if excerpt:
            break
    if not excerpt:
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) > 80:
                excerpt = text[:400] + ("..." if len(text) > 400 else "")
                break

    if not title and not excerpt:
        return None
    return {"title": title, "excerpt": excerpt}


# ─── Main worker ──────────────────────────────────────────────────────────────

async def _save_source(place_id, url: str, excerpt: str):
    async with AsyncSessionLocal() as db:
        ds = DataSource(
            place_id=place_id,
            source_type="article",
            source_name="וואלה! אוכל",
            url=url,
            excerpt=excerpt,
            confidence=0.7,
        )
        db.add(ds)
        await db.commit()


async def run_city_mode(city_filter: str | None, redo: bool, browser, client, all_places, already_done: set) -> int:
    """Search Walla by city via DDG — fast (16 searches) but misses English-named restaurants."""
    cities = [city_filter] if city_filter else WALLA_CITIES
    total_added = 0

    for city in cities:
        print(f"\n🏙️  {city}")
        urls = await _ddg_walla_urls(f'"{city}" ביקורת', client)
        print(f"  DDG נמצאו {len(urls)} כתובות")
        if not urls:
            await asyncio.sleep(2)
            continue

        city_places = [p for p in all_places if p.city and city in p.city] or all_places

        for url in urls:
            article = await _fetch_article(url, browser)
            if not article or not article["excerpt"]:
                continue

            title = article["title"]
            best_place, best_score = _best_match(title, city_places)

            if not best_place or best_score < 0.4:
                print(f"  ✗ no match (score={best_score:.2f}) — {title[:60]}")
                continue
            if str(best_place.id) in already_done:
                print(f"  ⏭  {best_place.name} already has Walla source")
                continue

            await _save_source(best_place.id, url, article["excerpt"])
            already_done.add(str(best_place.id))
            total_added += 1
            print(f"  ✓ {best_place.name} (score={best_score:.2f}): {article['excerpt'][:60]}...")

            await asyncio.sleep(0.5)

        await asyncio.sleep(3)

    return total_added


async def run_per_restaurant_mode(redo: bool, browser, client, all_places, already_done: set) -> int:
    """
    Search site:food.walla.co.il for each place by name — slower but finds
    articles for English-named and obscure restaurants.
    Skips places that already have a Walla source (unless --redo).
    """
    total_added = 0
    targets = [p for p in all_places if redo or str(p.id) not in already_done]
    print(f"\n🔍 Per-restaurant mode — {len(targets)} places to check")

    for i, place in enumerate(targets, 1):
        if str(place.id) in already_done and not redo:
            continue

        print(f"[{i}/{len(targets)}] {place.name}")
        urls = await _ddg_walla_urls(f'"{place.name}"', client, max_results=3)
        if not urls:
            await asyncio.sleep(1)
            continue

        for url in urls:
            article = await _fetch_article(url, browser)
            if not article or not article["excerpt"]:
                continue

            await _save_source(place.id, url, article["excerpt"])
            already_done.add(str(place.id))
            total_added += 1
            print(f"  ✓ {url.split('/')[-1]}: {article['excerpt'][:60]}...")
            break  # one Walla source per restaurant is enough

        await asyncio.sleep(1.5)

    return total_added


async def run(city_filter: str | None = None, redo: bool = False, per_restaurant: bool = False):
    if not HAS_PLAYWRIGHT:
        print("Playwright not installed — run `pip install playwright && playwright install chromium`")
        return

    async with AsyncSessionLocal() as db:
        all_places = list((await db.execute(select(Place))).scalars().all())

    already_done: set[str] = set()
    if not redo:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(DataSource.place_id)
                .where(DataSource.source_type == "article")
                .where(DataSource.source_name == "וואלה! אוכל")
            )).scalars().all()
            already_done = {str(r) for r in rows}

    async with httpx.AsyncClient() as client:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)

            if per_restaurant:
                total_added = await run_per_restaurant_mode(redo, browser, client, all_places, already_done)
            else:
                total_added = await run_city_mode(city_filter, redo, browser, client, all_places, already_done)

            await browser.close()

    print(f"\n✓ סיום — נוספו {total_added} ביקורות מ-Walla.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("city", nargs="?", help="Hebrew city name for city mode (default: all)")
    parser.add_argument("--per-restaurant", action="store_true", help="Search Walla per restaurant name (best coverage)")
    parser.add_argument("--redo", action="store_true", help="Overwrite existing Walla article sources")
    args = parser.parse_args()
    asyncio.run(run(city_filter=args.city, redo=args.redo, per_restaurant=args.per_restaurant))
