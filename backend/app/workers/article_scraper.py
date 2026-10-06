"""
Article scraper — fetches Israeli food blog pages and extracts excerpts.
Usage: poetry run python -m app.workers.article_scraper --place-slug taizu --url "https://rest.co.il/..."

Requires playwright browsers: poetry run playwright install chromium
"""

import asyncio
import argparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource
from app.services.places import get_place_by_slug


def extract_excerpt(html: str, max_chars: int = 200) -> str:
    """Pull the first meaningful paragraph from an article page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 60:
            return text[:max_chars] + ("..." if len(text) > max_chars else "")
    return ""


def infer_source_name(url: str) -> str:
    """Derive a human-readable source name from a URL."""
    from urllib.parse import urlparse
    host = urlparse(url).netloc.replace("www.", "")
    labels = {
        "rest.co.il": "rest.co.il",
        "mouse.co.il": "Mouse",
        "timeout.co.il": "TimeOut ישראל",
        "haaretz.co.il": "הארץ",
        "ynet.co.il": "Ynet",
        "walla.co.il": "וואלה!",
        "xnet.ynet.co.il": "Xnet",
    }
    for key, label in labels.items():
        if key in host:
            return label
    return host


async def scrape_article(place_slug: str, url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        await browser.close()

    excerpt = extract_excerpt(html)
    if not excerpt:
        print(f"לא נמצא תוכן ב-{url}")
        return

    source_name = infer_source_name(url)

    async with AsyncSessionLocal() as db:
        place = await get_place_by_slug(db, place_slug)
        if not place:
            print(f"המקום '{place_slug}' לא נמצא")
            return

        source = DataSource(
            place_id=place.id,
            source_type="article",
            source_name=source_name,
            url=url,
            excerpt=excerpt,
            confidence=0.6,
        )
        db.add(source)
        await db.commit()
        print(f"נשמר מאמר מ-{source_name}: {excerpt[:80]}...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--place-slug", required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    asyncio.run(scrape_article(args.place_slug, args.url))
