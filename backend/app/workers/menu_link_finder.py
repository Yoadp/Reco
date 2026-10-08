"""
Menu Link Finder — finds direct menu pages/PDFs on restaurant websites.

Strategy:
  1. Try common menu paths on the restaurant's own website (/menu, /תפריט, ...)
  2. Scrape the homepage for <a href> links containing "menu", "תפריט", or ".pdf"
  3. Never use ordering platforms (Wolt, ontopo, tabit) — those are for ordering, not reading menus.

Run:
    poetry run python -m app.workers.menu_link_finder           # all without menu_link yet
    poetry run python -m app.workers.menu_link_finder romano    # single slug
    poetry run python -m app.workers.menu_link_finder --redo    # redo all (overwrite)
"""
import asyncio
import re
import sys
import httpx
from urllib.parse import urljoin

from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

# These are ordering/reservation platforms — NOT menu viewers; skip them
ORDERING_DOMAINS = {"wolt.com", "ontopo.com", "tabit.co.il", "10bis.co.il", "tenbis.co.il"}

MENU_PATHS = ["/menu", "/תפריט", "/tafrit", "/our-menu", "/food-menu", "/menu.pdf"]

MENU_HREF_RE = re.compile(
    r'(?:^|/|=|-|_)(?:menu|תפריט|tafrit|our-menu|food-menu)(?:/|$|\.html|\?|-|_)|'
    r'\.pdf(?:\?[^"\']*)?$',
    re.IGNORECASE,
)
# Static asset extensions to skip — these match the regex but are not menu pages
SKIP_EXTENSIONS = re.compile(r'\.(css|js|woff|woff2|svg|ico|png|jpg|jpeg|gif|map|min\.[^/]+)(\?|$)', re.IGNORECASE)
SKIP_PATHS = re.compile(r'/(?:wp-content/plugins|wp-content/themes|assets/css|assets/js|elementor/css)/', re.IGNORECASE)

CONCURRENCY = 20  # parallel restaurant crawls


def _is_ordering_platform(url: str) -> bool:
    return any(d in url for d in ORDERING_DOMAINS)


async def _find_on_website(website: str, client: httpx.AsyncClient) -> str | None:
    base = website.rstrip("/")

    # 1. Try all common paths in parallel (HEAD requests)
    async def _try_path(path: str) -> str | None:
        try:
            r = await client.head(base + path, follow_redirects=True, timeout=3.0)
            if r.status_code < 400:
                return str(r.url)
        except Exception:
            pass
        return None

    path_results = await asyncio.gather(*[_try_path(p) for p in MENU_PATHS])
    for url in path_results:
        if url:
            return url

    # 2. Scrape homepage for menu-shaped <a href> links
    try:
        r = await client.get(website, follow_redirects=True, timeout=6.0)
        if r.status_code != 200:
            return None
        for href in re.findall(r'href=["\']([^"\']+)["\']', r.text, re.IGNORECASE):
            if MENU_HREF_RE.search(href) and not SKIP_EXTENSIONS.search(href) and not SKIP_PATHS.search(href):
                full = urljoin(str(r.url), href)
                if full.startswith("http") and not _is_ordering_platform(full):
                    return full
    except Exception:
        pass

    return None


async def process(slugs: list[str] | None = None, redo: bool = False):
    async with AsyncSessionLocal() as db:
        if slugs:
            stmt = select(Place).where(Place.slug.in_(slugs))
        elif redo:
            stmt = select(Place).where(Place.website.isnot(None)).order_by(Place.name)
        else:
            already = select(DataSource.place_id).where(DataSource.source_type == "menu_link").distinct()
            stmt = (
                select(Place)
                .where(Place.website.isnot(None))
                .where(Place.id.not_in(already))
                .order_by(Place.name)
            )

        result = await db.execute(stmt)
        places = list(result.scalars().all())

        real_places = [p for p in places if p.website and not _is_ordering_platform(p.website)]
        skipped_platform = len(places) - len(real_places)
        print(f"{len(places)} places — {skipped_platform} skipped (ordering platform), crawling {len(real_places)} in parallel ({CONCURRENCY} at a time)...")

        found = not_found = 0
        sem = asyncio.Semaphore(CONCURRENCY)

        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; Reco-bot/1.0)"},
            follow_redirects=True,
            timeout=httpx.Timeout(8.0),
        ) as client:

            async def handle_place(i: int, place: Place) -> None:
                nonlocal found, not_found
                async with sem:
                    if redo or slugs:
                        await db.execute(
                            delete(DataSource)
                            .where(DataSource.place_id == place.id)
                            .where(DataSource.source_type == "menu_link")
                        )
                        await db.flush()

                    menu_url = await _find_on_website(place.website, client)
                    if menu_url:
                        db.add(DataSource(
                            place_id=place.id,
                            source_type="menu_link",
                            source_name="תפריט",
                            url=menu_url,
                            confidence=0.85,
                        ))
                        await db.commit()
                        found += 1
                        print(f"  ✓ [{i}/{len(real_places)}] {place.name}: {menu_url[:70]}")
                    else:
                        not_found += 1
                        if not_found % 20 == 0:
                            print(f"  ... {not_found} not found so far")

            await asyncio.gather(*[handle_place(i + 1, p) for i, p in enumerate(real_places)])

        print(f"\nDone. Found {found} menu links ({not_found} not found, {skipped_platform} skipped).")


if __name__ == "__main__":
    args = sys.argv[1:]
    redo = "--redo" in args
    slugs = [a for a in args if not a.startswith("--")] or None
    asyncio.run(process(slugs=slugs, redo=redo))
