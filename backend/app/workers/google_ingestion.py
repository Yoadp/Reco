"""
Ingestion worker: pulls restaurants from Google Places API for a given city
and upserts them into the database.

Usage:
    python -m app.workers.google_ingestion --city "Tel Aviv" --query "restaurant"
"""

import asyncio
import argparse
import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import DataSource
from app.services.places import upsert_place_from_google

PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

DETAIL_FIELDS = "place_id,name,formatted_address,geometry,formatted_phone_number,website,opening_hours,photos,rating,price_level,types"


async def fetch_place_details(client: httpx.AsyncClient, place_id: str) -> dict:
    resp = await client.get(
        PLACES_DETAIL_URL,
        params={"place_id": place_id, "fields": DETAIL_FIELDS, "key": settings.google_places_api_key},
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


async def ingest_city(city: str, query: str = "restaurant", max_results: int = 60):
    if not settings.google_places_api_key:
        print("GOOGLE_PLACES_API_KEY not set — skipping ingestion")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        params = {"query": f"{query} in {city}", "key": settings.google_places_api_key}
        places_raw = []

        while len(places_raw) < max_results:
            resp = await client.get(PLACES_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            places_raw.extend(data.get("results", []))
            next_token = data.get("next_page_token")
            if not next_token:
                break
            params = {"pagetoken": next_token, "key": settings.google_places_api_key}
            await asyncio.sleep(2)  # required delay for next_page_token

        async with AsyncSessionLocal() as db:
            for raw in places_raw[:max_results]:
                try:
                    detail = await fetch_place_details(client, raw["place_id"])
                    normalized = {
                        "place_id": raw["place_id"],
                        "name": detail.get("name", raw.get("name", "")),
                        "formatted_address": detail.get("formatted_address", ""),
                        "city": city,
                        "lat": detail.get("geometry", {}).get("location", {}).get("lat"),
                        "lng": detail.get("geometry", {}).get("location", {}).get("lng"),
                        "formatted_phone_number": detail.get("formatted_phone_number"),
                        "website": detail.get("website"),
                        "opening_hours": detail.get("opening_hours"),
                        "rating": detail.get("rating"),
                        "price_level": detail.get("price_level"),
                        "photos": [p.get("photo_reference") for p in detail.get("photos", [])[:5]],
                    }
                    place = await upsert_place_from_google(db, normalized)
                    source = DataSource(
                        place_id=place.id,
                        source_type="google_places",
                        url=f"https://maps.google.com/?cid={raw['place_id']}",
                        raw_json=detail,
                        confidence=0.9,
                    )
                    db.add(source)
                    await db.flush()
                    print(f"  upserted: {place.name}")
                except Exception as exc:
                    print(f"  error for {raw.get('name', '?')}: {exc}")

            await db.commit()
    print(f"Done — processed up to {len(places_raw)} places in {city}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--query", default="restaurant")
    parser.add_argument("--max", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(ingest_city(args.city, args.query, args.max))
