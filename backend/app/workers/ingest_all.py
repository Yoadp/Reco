"""
Bulk ingestion runner — pulls restaurants from Google Places for all central Israel cities.

Usage:
    poetry run python -m app.workers.ingest_all

Cost estimate: ~$3 total (Google Places Text Search Legacy pricing).
Do NOT run app.workers.seed after this — seed.py deletes all places first.
"""

import asyncio
from app.workers.google_ingestion import ingest_city

TIER1 = {"תל אביב", "הרצליה", "נתניה", "ראשון לציון"}
TIER1_QUERIES = ["restaurant", "coffee", "bar", "sushi", "pizza", "hummus"]
TIER2_QUERIES = ["restaurant"]

ALL_CITIES = [
    ("תל אביב",     "תל אביב"),
    ("רמת גן",      "רמת גן"),
    ("גבעתיים",     "גבעתיים"),
    ("בני ברק",     "בני ברק"),
    ("פתח תקווה",   "פתח תקווה"),
    ("ראשון לציון", "ראשון לציון"),
    ("חולון",       "חולון"),
    ("בת ים",       "בת ים"),
    ("הרצליה",      "הרצליה"),
    ("רעננה",       "רעננה"),
    ("כפר סבא",     "כפר סבא"),
    ("הוד השרון",   "הוד השרון"),
    ("נתניה",       "נתניה"),
    ("רחובות",      "רחובות"),
    ("נס ציונה",    "Nes Ziona"),    # Hebrew stored in DB, English sent to Google API
    ("מודיעין",     "מודיעין"),
]
# Each tuple: (city_label stored in DB, query_name sent to Google)


async def main():
    total = 0
    for city_label, city_query in ALL_CITIES:
        queries = TIER1_QUERIES if city_label in TIER1 else TIER2_QUERIES
        for query in queries:
            print(f"\n=== {city_label} / {query} ===")
            query_city = city_query if city_query != city_label else None
            await ingest_city(city_label, query, max_results=60, query_city=query_city)
            total += 1
            await asyncio.sleep(1)

    print(f"\n✓ Done — ran {total} ingestion batches across {len(ALL_CITIES)} cities.")
    print("Next step: poetry run python -m app.workers.google_places_photos")


if __name__ == "__main__":
    asyncio.run(main())
