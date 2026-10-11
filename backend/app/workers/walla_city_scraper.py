"""
Walla Food city scraper — discovers restaurant reviews on food.walla.co.il
by scraping city-based search pages instead of searching DDG per-restaurant.

16 city pages → 100–200 matched article sources in ~5 minutes (vs 694 DDG searches).

Usage:
  poetry run python -m app.workers.walla_city_scraper           # all cities
  poetry run python -m app.workers.walla_city_scraper תל-אביב  # single city slug
  poetry run python -m app.workers.walla_city_scraper --redo    # overwrite existing
"""

import asyncio
import argparse
import re
import sys
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from sqlalchemy import select, func

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


# ─── Name matching (from wolt_enrichment.py pattern) ─────────────────────────

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
    # "ביקורת: NAME" or "ביקורת | NAME" or "ביקורת - NAME"
    m = re.search(r"ביקורת[:\|\-–]\s*(.+?)(?:\s*[-–\|]|$)", title)
    if m:
        return m.group(1).strip()
    # "NAME - ביקורת" or "NAME | ביקורת"
    m = re.search(r"^(.+?)\s*[-–\|]\s*ביקורת", title)
    if m:
        return m.group(1).strip()
    # "NAME | וואלה אוכל"
    m = re.search(r"^(.+?)\s*[\|–-]", title)
    if m:
        return m.group(1).strip()
    return title.strip()


# ─── Walla page fetching ──────────────────────────────────────────────────────

async def _fetch_walla_search(city: str) -> list[dict]:
    """
    Scrape Walla food search for a given city.
    Returns list of {title, url, excerpt} dicts.
    """
    if not HAS_PLAYWRIGHT:
        print("  Playwright not installed — skipping")
        return []

    query = quote_plus(f"{city} ביקורת מסעדה")
    url = f"https://food.walla.co.il/?s={query}"
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)  # let JS render
            html = await page.content()
        except Exception as e:
            print(f"  Playwright fetch error: {e}")
            await browser.close()
            return []
        await browser.close()

    soup = BeautifulSoup(html, "lxml")
    for article in soup.select("article, .post, .item, .search-result"):
        link = article.select_one("a[href*='food.walla.co.il']") or article.select_one("h2 a, h3 a, .title a")
        if not link:
            continue
        href = link.get("href", "")
        if not href.startswith("http"):
            continue
        title = link.get_text(" ", strip=True)
        # Skip if not a review article
        if not any(kw in title for kw in ["ביקורת", "מסעדה", "שף", "אוכל"]) and "food.walla.co.il/item" not in href:
            continue
        excerpt_el = article.select_one("p, .excerpt, .description, .lead")
        excerpt = excerpt_el.get_text(" ", strip=True)[:400] if excerpt_el else ""
        results.append({"title": title, "url": href, "excerpt": excerpt})

    # If article-based selectors found nothing, try generic link approach
    if not results:
        for a in soup.select("a[href*='food.walla.co.il/item']"):
            href = a.get("href", "")
            title = a.get_text(" ", strip=True)
            if title and len(title) > 5:
                results.append({"title": title, "url": href, "excerpt": ""})

    return results[:30]  # cap per city


async def _fetch_excerpt(url: str) -> str:
    """Fetch a Walla article page and extract excerpt."""
    if not HAS_PLAYWRIGHT:
        return ""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
            html = await page.content()
        except Exception:
            await browser.close()
            return ""
        await browser.close()

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    for selector in ["article", ".article-body", ".post-content", ".entry-content", "main"]:
        container = soup.select_one(selector)
        if container:
            for p in container.find_all("p"):
                text = p.get_text(" ", strip=True)
                if len(text) > 80:
                    return text[:400] + ("..." if len(text) > 400 else "")
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) > 80:
            return text[:400] + ("..." if len(text) > 400 else "")
    return ""


# ─── Main worker ──────────────────────────────────────────────────────────────

async def run(city_filter: str | None = None, redo: bool = False):
    cities = [city_filter] if city_filter else WALLA_CITIES

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Place))
        all_places = list(result.scalars().all())

    already_done: set[str] = set()
    if not redo:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DataSource.place_id)
                .where(DataSource.source_type == "article")
                .where(DataSource.source_name == "וואלה! אוכל")
            )
            already_done = {str(r) for r in result.scalars().all()}

    total_added = 0

    for city in cities:
        print(f"\n🏙️  {city}")
        articles = await _fetch_walla_search(city)
        print(f"  נמצאו {len(articles)} תוצאות ב-Walla")

        for art in articles:
            name_from_title = _extract_restaurant_name(art["title"])

            # Find best matching place in this city
            city_places = [p for p in all_places if p.city and city in p.city]
            if not city_places:
                city_places = all_places  # fallback: search all

            best_place = None
            best_score = 0.0
            for place in city_places:
                score = _name_similarity(place.name, name_from_title)
                if score > best_score:
                    best_score = score
                    best_place = place

            if not best_place or best_score < 0.45:
                continue
            if str(best_place.id) in already_done:
                continue

            # Fetch excerpt from article page if not already available
            excerpt = art["excerpt"]
            if not excerpt and art["url"]:
                excerpt = await _fetch_excerpt(art["url"])

            if not excerpt:
                continue

            async with AsyncSessionLocal() as db:
                source = DataSource(
                    place_id=best_place.id,
                    source_type="article",
                    source_name="וואלה! אוכל",
                    url=art["url"],
                    excerpt=excerpt,
                    confidence=0.7,
                )
                db.add(source)
                await db.commit()
                already_done.add(str(best_place.id))
                total_added += 1
                print(f"  ✓ {best_place.name} (score={best_score:.2f}): {excerpt[:60]}...")

        await asyncio.sleep(2)  # polite pause between cities

    print(f"\n✓ סיום — נוספו {total_added} ביקורות מ-Walla.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("city", nargs="?", help="Hebrew city name to process (default: all)")
    parser.add_argument("--redo", action="store_true", help="Overwrite existing Walla article sources")
    args = parser.parse_args()
    asyncio.run(run(city_filter=args.city, redo=args.redo))
