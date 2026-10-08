"""
Fetches real restaurant photos from the Google Places API (New) and saves them to the DB.
For each place that has no photos, searches by name+city, pulls photo references,
resolves them to final image URLs, and stores them.

Usage:
  poetry run python -m app.workers.google_places_photos          # all places without photos
  poetry run python -m app.workers.google_places_photos --slug miznon  # one place
"""
import asyncio
import argparse
import httpx
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import Place

BASE = "https://places.googleapis.com/v1"

# English name hints for better search accuracy
EN_NAMES: dict[str, str] = {
    "אבו חסן": "Abu Hassan hummus Jaffa",
    "טאיזו": "Taizu Asian fusion Tel Aviv",
    "בר החומוס": "The Hummus Bar Dizengoff Tel Aviv",
    "מזנון": "Miznon street food Tel Aviv",
    "סושי סמבה": "Sushi Samba Tel Aviv",
    "שילה": "Shila seafood Tel Aviv",
    "פסטה נוסטרה": "Pasta Nostra Rothschild Tel Aviv",
    "פרונטו": "Pronto pizza Herzl Tel Aviv",
    "פורט סעיד": "Port Said restaurant Tel Aviv",
    "ננוצ'קה": "Nanuchka Georgian vegan Tel Aviv",
    "קיצ'ן מרקט": "Kitchen Market Carmel Tel Aviv",
    "הבסטה": "HaBasta bistro Tel Aviv",
    "קלארו": "Claro Latin restaurant Tel Aviv",
    "רומנו": "Romano Eyal Shani Rothschild Tel Aviv",
    'ד"ר שקשוקה': "Dr Shakshuka Jaffa Tel Aviv",
    "דלאל": "Dallal French bistro Jaffa Tel Aviv",
    "בנדיקט": "Benedict all day breakfast Tel Aviv",
    "הקוסם": "HaKosem falafel Tel Aviv",
    "ברוטו": "Bruto pasta bar Tel Aviv",
    "קאטית": "Catit chef restaurant Tel Aviv",
    "אגדיר": "Agadir burger Tel Aviv",
    "שקשוקיה": "Shakshukiya breakfast Tel Aviv",
    "קלמטה": "Kalamata Greek Tel Aviv",
    "אוזריה": "Ouzeria Greek bar Tel Aviv",
    "ביציקלטה": "Bicicletta Italian pizza Tel Aviv",
    "סאלה תאי": "Sala Thai restaurant Tel Aviv",
    "קפה נואר": "Cafe Noir bistro Tel Aviv",
    "מסה": "Messa chef restaurant Tel Aviv",
    "האוז'ריה": "fish restaurant Jaffa port Tel Aviv",
    "השולחן": "HaShulchan Israeli restaurant Tel Aviv",
}


async def fetch_place_data(
    client: httpx.AsyncClient, name: str, city: str, api_key: str, max_photos: int = 4
) -> dict:
    """Returns {"photos": [...urls], "website": str|None}"""
    query = EN_NAMES.get(name, f"{name} restaurant {city}")

    r = await client.post(
        f"{BASE}/places:searchText",
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.photos,places.websiteUri",
            "Content-Type": "application/json",
            "Referer": "http://localhost:3000",
        },
        json={"textQuery": query, "maxResultCount": 1, "languageCode": "he"},
    )
    results = r.json().get("places", [])
    if not results:
        print(f"  ✗ לא נמצא: {name}")
        return {"photos": [], "website": None}

    place = results[0]
    display = place.get("displayName", {}).get("text", "?")
    website = place.get("websiteUri")
    photos_data = place.get("photos", [])[:max_photos]

    print(f"  ✓ נמצא: {display}{' 🌐' if website else ''} — {len(photos_data)} תמונות")

    # Store the reference name (e.g. "places/ChIJ.../photos/AXCi2y...")
    # These never expire. The frontend constructs the URL using the public API key.
    refs = [ph["name"] for ph in photos_data if ph.get("name")]
    return {"photos": refs, "website": website}


async def run(slug_filter: str | None = None, refresh: bool = False):
    api_key = settings.google_places_api_key
    if not api_key:
        print("GOOGLE_PLACES_API_KEY לא מוגדר ב-.env")
        return

    async with AsyncSessionLocal() as db:
        stmt = select(Place)
        if slug_filter:
            stmt = stmt.where(Place.slug == slug_filter)
        result = await db.execute(stmt)
        places = result.scalars().all()

        refreshed = skipped = 0
        async with httpx.AsyncClient(timeout=20.0) as client:
            for place in places:
                has_photos = bool(place.photos)
                has_website = bool(place.website)
                # Skip only when we already have both and not forcing a refresh
                if has_photos and has_website and not slug_filter and not refresh:
                    skipped += 1
                    continue
                print(f"מחפש: {place.name}")
                data = await fetch_place_data(client, place.name, place.city, api_key)
                updates: dict = {}
                if data["photos"]:
                    updates["photos"] = data["photos"]
                    print(f"    נשמרו {len(data['photos'])} תמונות")
                if data["website"] and not has_website:
                    updates["website"] = data["website"]
                    print(f"    אתר: {data['website']}")
                if updates:
                    await db.execute(update(Place).where(Place.id == place.id).values(**updates))
                    await db.commit()
                    refreshed += 1

    print(f"סיום. רוענן: {refreshed}, דולג: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None)
    parser.add_argument("--refresh", action="store_true", help="Force-refresh photos for all places (URLs expire)")
    args = parser.parse_args()
    asyncio.run(run(slug_filter=args.slug, refresh=args.refresh))
