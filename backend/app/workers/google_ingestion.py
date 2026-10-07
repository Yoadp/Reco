"""
Ingestion worker: pulls restaurants from Google Places API (New) for a given city
and upserts them into the database.

Usage:
    python -m app.workers.google_ingestion --city "תל אביב" --query "restaurant"
"""

import asyncio
import argparse
import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import DataSource
from app.services.places import upsert_place_from_google
from app.workers.backfill_cuisine import map_type_to_cuisine

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.priceLevel,"
    "places.websiteUri,places.nationalPhoneNumber,"
    "places.regularOpeningHours,places.primaryTypeDisplayName,"
    "places.photos"
)

PRICE_MAP = {
    "PRICE_LEVEL_FREE":           1,
    "PRICE_LEVEL_INEXPENSIVE":    1,
    "PRICE_LEVEL_MODERATE":       2,
    "PRICE_LEVEL_EXPENSIVE":      3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


def _normalize(raw: dict, city: str) -> dict:
    """Map New Places API response fields to the dict upsert_place_from_google expects."""
    loc = raw.get("location", {})
    price_str = raw.get("priceLevel", "")
    hours = raw.get("regularOpeningHours", {})
    photos = [p["name"] for p in raw.get("photos", [])[:5] if "name" in p]
    type_text = raw.get("primaryTypeDisplayName", {}).get("text") if isinstance(raw.get("primaryTypeDisplayName"), dict) else None

    return {
        "place_id":              raw.get("id", ""),
        "name":                  raw.get("displayName", {}).get("text", ""),
        "formatted_address":     raw.get("formattedAddress", ""),
        "city":                  city,
        "lat":                   loc.get("latitude"),
        "lng":                   loc.get("longitude"),
        "formatted_phone_number": raw.get("nationalPhoneNumber"),
        "website":               raw.get("websiteUri"),
        "opening_hours":         hours if hours else None,
        "rating":                raw.get("rating"),
        "price_level":           PRICE_MAP.get(price_str),
        "photos":                photos if photos else None,
        "cuisine":               map_type_to_cuisine(type_text) or ["ישראלי"],
    }


async def ingest_city(city: str, query: str = "restaurant", max_results: int = 60, query_city: str | None = None):
    """city = Hebrew label stored in DB. query_city = string sent to Google API (use English for better results)."""
    if not settings.google_places_api_key:
        print("GOOGLE_PLACES_API_KEY not set — skipping ingestion")
        return

    headers = {
        "Content-Type":   "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
        "Referer": "http://localhost:3000",
    }

    places_raw: list[dict] = []
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while len(places_raw) < max_results:
            body: dict = {
                "textQuery":     f"{query} in {query_city or city}",
                "maxResultCount": min(20, max_results - len(places_raw)),
                "languageCode":  "he",
            }
            if page_token:
                body["pageToken"] = page_token

            resp = await client.post(PLACES_SEARCH_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

            batch = data.get("places", [])
            places_raw.extend(batch)
            page_token = data.get("nextPageToken")
            if not page_token or not batch:
                break
            await asyncio.sleep(2)  # required delay between pages

        async with AsyncSessionLocal() as db:
            for raw in places_raw:
                try:
                    normalized = _normalize(raw, city)
                    if not normalized["name"]:
                        continue
                    place = await upsert_place_from_google(db, normalized)
                    # Add google_places DataSource if not already present
                    source = DataSource(
                        place_id=place.id,
                        source_type="google_places",
                        source_name="Google",
                        url=f"https://maps.google.com/?cid={raw.get('id', '')}",
                        confidence=0.9,
                        raw_json=raw,
                    )
                    db.add(source)
                    await db.flush()
                    print(f"  upserted: {place.name} ({place.city})")
                except Exception as exc:
                    name = raw.get("displayName", {}).get("text", "?")
                    print(f"  error for {name}: {exc}")

            await db.commit()

    print(f"Done — processed {len(places_raw)} places in {city}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--query", default="restaurant")
    parser.add_argument("--max", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(ingest_city(args.city, args.query, args.max))
