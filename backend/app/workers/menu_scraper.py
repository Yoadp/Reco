"""
Menu scraper — extracts menu data from Tabit, Ontopo, or a restaurant's own website.
Usage: poetry run python -m app.workers.menu_scraper --place-slug taizu --url "https://tabit.cloud/..." --source-type tabit

Requires playwright browsers: poetry run playwright install chromium
"""

import asyncio
import argparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource
from app.services.places import get_place_by_slug

SOURCE_NAMES = {
    "tabit": "Tabit",
    "ontopo": "Ontopo",
    "wolt": "Wolt",
    "website": None,  # will use domain
}

SOURCE_CONFIDENCE = {
    "tabit": 0.75,
    "ontopo": 0.7,
    "wolt": 0.7,
    "website": 0.65,
}


def extract_menu_excerpt(html: str, max_chars: int = 200) -> str:
    """Try to pull dish names / menu section headings from a page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # Look for lists or headings that likely contain menu items
    candidates = []
    for el in soup.find_all(["h2", "h3", "li", "span"]):
        text = el.get_text(strip=True)
        if 3 < len(text) < 60 and not any(c.isdigit() for c in text[:3]):
            candidates.append(text)
        if len(candidates) >= 6:
            break

    if candidates:
        excerpt = "תפריט: " + ", ".join(candidates[:5])
        return excerpt[:max_chars]
    return ""


async def scrape_menu(place_slug: str, url: str, source_type: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=45000)
        html = await page.content()
        await browser.close()

    excerpt = extract_menu_excerpt(html)
    source_name = SOURCE_NAMES.get(source_type) or url.split("/")[2].replace("www.", "")
    confidence = SOURCE_CONFIDENCE.get(source_type, 0.65)

    async with AsyncSessionLocal() as db:
        place = await get_place_by_slug(db, place_slug)
        if not place:
            print(f"המקום '{place_slug}' לא נמצא")
            return

        source = DataSource(
            place_id=place.id,
            source_type=source_type,
            source_name=source_name,
            url=url,
            excerpt=excerpt or "תפריט זמין בקישור",
            raw_json={"scraped_url": url},
            confidence=confidence,
        )
        db.add(source)
        await db.commit()
        print(f"נשמר תפריט מ-{source_name}: {excerpt[:80] if excerpt else '(ללא תוכן)'}...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--place-slug", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--source-type", default="menu", choices=["tabit", "ontopo", "wolt", "website", "menu"])
    args = parser.parse_args()
    asyncio.run(scrape_menu(args.place_slug, args.url, args.source_type))
