"""
Fetch Google Places reviews for all places and store them as DataSource rows.

Uses the Places (New) Details endpoint — costs ~$0.017 per place (Advanced SKU).
Skips places that already have a review excerpt.

Usage:
    poetry run python -m app.workers.backfill_google_reviews
"""

import asyncio
import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

PLACE_DETAIL_URL = "https://places.googleapis.com/v1/places/{place_id}"
FIELD_MASK = "reviews,rating,userRatingCount"


async def fetch_reviews(client: httpx.AsyncClient, google_place_id: str) -> dict:
    url = PLACE_DETAIL_URL.format(place_id=google_place_id)
    resp = await client.get(
        url,
        headers={
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "Referer": "http://localhost:3000",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def backfill():
    if not settings.google_places_api_key:
        print("GOOGLE_PLACES_API_KEY not set")
        return

    async with AsyncSessionLocal() as db:
        # Get all places with a google_place_id that have no excerpt yet
        result = await db.execute(
            select(Place, DataSource)
            .join(DataSource, DataSource.place_id == Place.id)
            .where(
                Place.google_place_id.isnot(None),
                DataSource.source_type == "google_places",
                DataSource.excerpt.is_(None),
            )
        )
        rows = result.fetchall()

    # Deduplicate — one entry per place
    seen = set()
    targets = []
    for place, source in rows:
        if place.id not in seen:
            seen.add(place.id)
            targets.append((place.id, place.name, place.google_place_id, source.id))

    print(f"Fetching reviews for {len(targets)} places…")

    async with httpx.AsyncClient(timeout=15) as client:
        for i, (place_id, name, google_id, source_id) in enumerate(targets):
            try:
                data = await fetch_reviews(client, google_id)

                reviews = data.get("reviews", [])
                rating = data.get("rating")
                review_count = data.get("userRatingCount")

                # Pick the longest review text as excerpt
                best_review = max(
                    reviews,
                    key=lambda r: len(r.get("text", {}).get("text", "")),
                    default=None,
                )
                excerpt = None
                if best_review:
                    excerpt = best_review.get("text", {}).get("text", "")[:500]

                async with AsyncSessionLocal() as db:
                    ds = await db.get(DataSource, source_id)
                    if ds:
                        if excerpt:
                            ds.excerpt = excerpt
                        if review_count:
                            ds.review_count = review_count
                    # Also update aggregated_score if we now have a rating
                    place = await db.get(Place, place_id)
                    if place and rating and not place.aggregated_score:
                        place.aggregated_score = rating
                    await db.commit()

                status = f"✓ {len(reviews)} reviews" if reviews else "— no reviews"
                print(f"  [{i+1}/{len(targets)}] {name[:35]:<35} {status}")

            except Exception as e:
                print(f"  [{i+1}/{len(targets)}] {name[:35]:<35} ERROR: {e}")

            # Small delay to avoid hitting rate limits
            if (i + 1) % 10 == 0:
                await asyncio.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(backfill())
