"""
Bulk article finder — discovers blog/review articles for restaurants and saves them as DataSource rows.

For each restaurant it:
1. Searches DuckDuckGo HTML for '{name} {city} ביקורת' (or Google Custom Search if configured)
2. Filters results to known Israeli review domains
3. Scrapes each found URL for a meaningful excerpt (httpx first, Playwright fallback)
4. Stores as DataSource(source_type='article') rows
5. Skips places that already have article sources (pass --redo to override)

Usage:
  poetry run python -m app.workers.bulk_article_finder             # all places
  poetry run python -m app.workers.bulk_article_finder romano      # single slug
  poetry run python -m app.workers.bulk_article_finder --redo      # re-search all
  poetry run python -m app.workers.bulk_article_finder --limit 50  # first 50 places

Environment (optional, in backend/.env):
  GOOGLE_SEARCH_CX=<Custom Search Engine ID>   → uses Google Custom Search (100 req/day free)
  # GOOGLE_PLACES_API_KEY is reused as the search key when GOOGLE_SEARCH_CX is set
"""

import asyncio
import argparse
import re
import sys
import time
from urllib.parse import urlparse, quote_plus
from bs4 import BeautifulSoup
import httpx
from sqlalchemy import select, func

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.place import Place, DataSource


# ─── Domains we consider trustworthy review/article sources ──────────────────

# Known source name labels for common Israeli review sites
SOURCE_LABELS: dict[str, str] = {
    "rest.co.il":         "rest.co.il",
    "timeout.co.il":      "TimeOut ישראל",
    "mouse.co.il":        "Mouse",
    "haaretz.co.il":      "הארץ",
    "themarker.com":      "TheMarker",
    "walla.co.il":        "וואלה! אוכל",
    "food.walla.co.il":   "וואלה! אוכל",
    "ynet.co.il":         "Ynet",
    "mako.co.il":         "מאקו",
    "calcalist.co.il":    "כלכליסט",
    "maariv.co.il":       "מעריב",
    "israelhayom.co.il":  "ישראל היום",
    "nrg.co.il":          "NRG",
    "jpost.com":          "Jerusalem Post",
    "timesofisrael.com":  "Times of Israel",
    "israel21c.org":      "Israel21c",
    "tripadvisor.co.il":  "TripAdvisor",
    "tripadvisor.com":    "TripAdvisor",
}

# Skip these — they're booking/aggregator/ordering platforms with no article content
BLOCKLIST_SUBSTRINGS = [
    "maps.google", "google.com/maps",
    "wolt.com", "10bis.co.il", "mishloha.co.il", "dostavista",
    "ontopo.com", "tabitisrael.co.il",
    "booking.com", "airbnb",
    "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
    "linkedin.com", "youtube.com",
    "rest.co.il",   # JS-rendered, blocks scrapers
    "resty.co.il",  # aggregator
    "zips.co.il",   # aggregator
    "easy.co.il",   # aggregator
    "zap.co.il",    # aggregator
]

# These sites need Playwright (JS-heavy); httpx won't extract meaningful content
PLAYWRIGHT_DOMAINS = [
    "walla.co.il",
    "ynet.co.il", "mako.co.il",
    "tripadvisor", "maariv.co.il",
    "israelhayom.co.il", "haaretz.co.il",
    "themarker.com", "calcalist.co.il",
]

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


# ─── URL discovery ────────────────────────────────────────────────────────────

def _should_include(url: str) -> tuple[bool, str]:
    """Return (include, source_name). Block aggregators; accept everything else."""
    url_lower = url.lower()
    for block in BLOCKLIST_SUBSTRINGS:
        if block in url_lower:
            return False, ""
    # Derive a human-readable source name
    host = urlparse(url).netloc.lower().replace("www.", "")
    for domain, label in SOURCE_LABELS.items():
        if domain in host:
            return True, label
    # Unknown domain — still include (could be a food blog); use the hostname as label
    return True, host


def _needs_playwright(url: str) -> bool:
    """Return True if this URL requires Playwright (JS-rendered page)."""
    url_lower = url.lower()
    return any(d in url_lower for d in PLAYWRIGHT_DOMAINS)


async def _search_duckduckgo(query: str, client: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Search DuckDuckGo HTML endpoint and return [(url, source_name)] for review domains."""
    try:
        r = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "il-he"},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "he-IL,he;q=0.9,en;q=0.8"},
            timeout=12.0,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            # DDG wraps URLs — extract the real URL
            m = re.search(r'uddg=([^&]+)', href)
            url = m.group(1) if m else href
            from urllib.parse import unquote
            url = unquote(url)
            if url.startswith("http"):
                ok, label = _should_include(url)
                if ok:
                    results.append((url, label))
        # Sort: prefer known high-quality domains first
        PRIORITY = ["walla.co.il", "timeout.co.il", "maariv.co.il", "haaretz.co.il", "ynet.co.il", "mako.co.il"]
        results.sort(key=lambda x: next((i for i, d in enumerate(PRIORITY) if d in x[0]), len(PRIORITY)))
        return results[:4]  # cap at 4 per restaurant
    except Exception as e:
        print(f"    DDG error: {e}")
        return []


async def _search_google_cse(query: str, cx: str, api_key: str, client: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Google Custom Search JSON API — requires a CSE ID configured in .env as GOOGLE_SEARCH_CX."""
    try:
        r = await client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"q": query, "cx": cx, "key": api_key, "num": 5, "lr": "lang_he"},
            timeout=10.0,
        )
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        results = []
        for item in items:
            url = item.get("link", "")
            ok, label = _should_include(url)
            if ok:
                results.append((url, label))
        return results[:3]
    except Exception as e:
        print(f"    Google CSE error: {e}")
        return []


# ─── Article scraping ─────────────────────────────────────────────────────────

def _extract_excerpt(html: str, max_chars: int = 300) -> str:
    """Extract the first meaningful paragraph from article HTML."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    # Try article body first
    for selector in ["article", ".article-body", ".post-content", ".entry-content", "main"]:
        container = soup.select_one(selector)
        if container:
            for p in container.find_all("p"):
                text = p.get_text(" ", strip=True)
                if len(text) > 80:
                    return text[:max_chars] + ("..." if len(text) > max_chars else "")
    # Fallback: any paragraph
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) > 80:
            return text[:max_chars] + ("..." if len(text) > max_chars else "")
    return ""


async def _scrape_url_httpx(url: str, client: httpx.AsyncClient) -> str:
    """Fetch URL with httpx and extract an excerpt. Fast but fails on JS-heavy pages."""
    try:
        r = await client.get(url, timeout=10.0, follow_redirects=True)
        if r.status_code != 200:
            return ""
        return _extract_excerpt(r.text)
    except Exception:
        return ""


async def _scrape_url_playwright(url: str) -> str:
    """Playwright fallback for JS-rendered pages."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            html = await page.content()
            await browser.close()
        return _extract_excerpt(html)
    except Exception:
        return ""


async def _scrape(url: str, client: httpx.AsyncClient) -> str:
    """Scrape a URL for an article excerpt.
    Known JS-heavy domains use Playwright directly; everything else tries httpx first."""
    if _needs_playwright(url):
        return await _scrape_url_playwright(url)
    excerpt = await _scrape_url_httpx(url, client)
    if not excerpt:
        excerpt = await _scrape_url_playwright(url)
    return excerpt


# ─── Main worker ──────────────────────────────────────────────────────────────

async def run(slug_filter: str | None = None, redo: bool = False, limit: int | None = None):
    google_cx = getattr(settings, "google_search_cx", "")
    use_google = bool(google_cx and settings.google_places_api_key)
    search_method = "Google CSE" if use_google else "DuckDuckGo"
    print(f"Article finder starting — search engine: {search_method}")

    async with AsyncSessionLocal() as db:
        stmt = select(Place).order_by(Place.name)
        if slug_filter:
            stmt = stmt.where(Place.slug == slug_filter)
        result = await db.execute(stmt)
        places = list(result.scalars().all())

        if not redo:
            # Skip places that already have at least one article source
            article_place_ids_result = await db.execute(
                select(DataSource.place_id)
                .where(DataSource.source_type == "article")
                .distinct()
            )
            already_done = set(str(r) for r in article_place_ids_result.scalars().all())
            before = len(places)
            places = [p for p in places if str(p.id) not in already_done]
            print(f"Skipping {before - len(places)} places that already have articles")

        if limit:
            places = places[:limit]

        print(f"Processing {len(places)} places\n")

    total_added = 0
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        for i, place in enumerate(places, 1):
            name = place.name
            city = place.city or ""
            # Strip English subtitle / sub-brand after | or – (confuses search engines)
            clean_name = re.split(r'[|–—]', name)[0].strip()
            query = f'"{clean_name}" {city} ביקורת מסעדה'
            print(f"[{i}/{len(places)}] {name}")

            if use_google:
                found_urls = await _search_google_cse(query, google_cx, settings.google_places_api_key, client)
            else:
                found_urls = await _search_duckduckgo(query, client)
                # Targeted walla search (most reliable Israeli food review source)
                if not any("walla.co.il" in u for u, _ in found_urls):
                    walla_query = f'{clean_name} {city} site:food.walla.co.il'
                    walla_results = await _search_duckduckgo(walla_query, client)
                    found_urls = walla_results + found_urls
                    await asyncio.sleep(1.5)
                # Fallback for English-name restaurants: try English query too
                if not found_urls and not any('א' <= c <= 'ת' for c in clean_name):
                    en_query = f'"{clean_name}" {city} restaurant review Israel'
                    found_urls = await _search_duckduckgo(en_query, client)
                    await asyncio.sleep(1.5)

            if not found_urls:
                print(f"  לא נמצאו תוצאות")
                await asyncio.sleep(2)
                continue

            place_added = 0
            async with AsyncSessionLocal() as db:
                # Re-fetch place to get its ID fresh in this session
                result = await db.execute(select(Place).where(Place.id == place.id))
                db_place = result.scalar_one_or_none()
                if not db_place:
                    continue

                # Get existing article URLs for this place to avoid duplicates
                existing_result = await db.execute(
                    select(DataSource.url)
                    .where(DataSource.place_id == place.id)
                    .where(DataSource.source_type == "article")
                )
                existing_urls = set(existing_result.scalars().all())

                for url, label in found_urls:
                    if url in existing_urls:
                        print(f"  ↩ כבר קיים: {url[:60]}")
                        continue

                    excerpt = await _scrape(url, client)
                    if not excerpt:
                        print(f"  ✗ לא נמצא תוכן: {url[:60]}")
                        await asyncio.sleep(1)
                        continue

                    source = DataSource(
                        place_id=db_place.id,
                        source_type="article",
                        source_name=label,
                        url=url,
                        excerpt=excerpt,
                        confidence=0.65,
                    )
                    db.add(source)
                    print(f"  ✓ {label}: {excerpt[:80]}...")
                    place_added += 1
                    await asyncio.sleep(1.5)

                if place_added:
                    await db.commit()
                    total_added += place_added

            # Polite delay between restaurants (DDG rate limit)
            await asyncio.sleep(2.5)

    print(f"\nסיום. נוספו {total_added} מאמרים חדשים.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", nargs="?", help="Process a single restaurant by slug")
    parser.add_argument("--redo", action="store_true", help="Re-search places that already have articles")
    parser.add_argument("--limit", type=int, help="Max number of places to process")
    args = parser.parse_args()
    asyncio.run(run(slug_filter=args.slug, redo=args.redo, limit=args.limit))
