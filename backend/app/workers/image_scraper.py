"""
Image scraper — fetches real photos from a restaurant's own website.
Tries og:image meta tags first, then large <img> elements.
Saves up to `max_images` URLs into the place's photos array.

Usage:
  poetry run python -m app.workers.image_scraper --place-slug port-said --url https://www.portsaid.co.il
  poetry run python -m app.workers.image_scraper --place-slug nanuchka --url https://www.nanuchka.co.il
"""
import asyncio
import argparse
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.place import Place
from app.services.places import get_place_by_slug


def is_valid_image_url(url: str) -> bool:
    if not url or len(url) > 500:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
    # skip icons, logos, tiny tracker pixels
    skip = ("icon", "logo", "favicon", "pixel", "tracker", "1x1", "avatar", "badge")
    if any(s in path for s in skip):
        return False
    return True


async def scrape_images(place_slug: str, url: str, max_images: int = 4) -> list[str]:
    images: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # wait a moment for JS-rendered content and redirects to settle
            await page.wait_for_timeout(2000)
            html = await page.content()
        except Exception as e:
            # Try grabbing whatever HTML loaded so far
            try:
                html = await page.content()
                if len(html) < 500:
                    raise e
            except Exception:
                print(f"שגיאה בטעינת הדף: {e}")
                await browser.close()
                return []
        await browser.close()

    soup = BeautifulSoup(html, "lxml")
    base = url

    # 1. Open Graph image (usually the best hero image)
    for prop in ("og:image", "twitter:image", "og:image:secure_url"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            img = urljoin(base, tag["content"])
            if is_valid_image_url(img) and img not in images:
                images.append(img)

    # 2. Large <img> tags — prefer ones likely to be restaurant/food photography
    for img_tag in soup.find_all("img"):
        src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src")
        if not src:
            continue
        src = urljoin(base, src)
        if not is_valid_image_url(src) or src in images:
            continue
        # Prefer images with food/restaurant hints in their path
        path_lower = src.lower()
        priority = any(k in path_lower for k in ("food", "dish", "restaurant", "photo", "gallery", "menu", "image"))
        if priority:
            images.insert(min(1, len(images)), src)
        else:
            images.append(src)
        if len(images) >= max_images * 2:
            break

    return images[:max_images]


async def save_images(place_slug: str, image_urls: list[str]):
    async with AsyncSessionLocal() as db:
        place = await get_place_by_slug(db, place_slug)
        if not place:
            print(f"המקום '{place_slug}' לא נמצא")
            return
        await db.execute(
            update(Place).where(Place.id == place.id).values(photos=image_urls)
        )
        await db.commit()
        print(f"נשמרו {len(image_urls)} תמונות עבור {place.name}")
        for u in image_urls:
            print(f"  • {u}")


async def run(place_slug: str, url: str):
    print(f"סורק תמונות מ: {url}")
    images = await scrape_images(place_slug, url)
    if not images:
        print("לא נמצאו תמונות")
        return
    await save_images(place_slug, images)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--place-slug", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--max", type=int, default=4)
    args = parser.parse_args()
    asyncio.run(run(args.place_slug, args.url))
