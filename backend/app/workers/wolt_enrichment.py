"""
Match our restaurants to Wolt venues by coordinates/name and add DataSource rows.

Uses Wolt's public consumer API — no API key required.

Usage:
    poetry run python -m app.workers.wolt_enrichment
"""

import asyncio
import math
import re
import httpx
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

WOLT_API = "https://consumer-api.wolt.com/v1/pages/restaurants"
WOLT_BASE = "https://wolt.com/il/isr"

# Coordinate grid points per city — multiple points give broader coverage
CITY_COORDS: dict[str, list[tuple[float, float]]] = {
    "תל אביב":     [(32.0853, 34.7818), (32.0650, 34.7750), (32.1050, 34.7900)],
    "רמת גן":      [(32.0681, 34.8238)],
    "גבעתיים":     [(32.0706, 34.8109)],
    "בני ברק":     [(32.0833, 34.8340)],
    "פתח תקווה":   [(32.0869, 34.8878)],
    "ראשון לציון": [(31.9642, 34.8007), (31.9800, 34.7900)],
    "חולון":       [(32.0107, 34.7795)],
    "בת ים":       [(32.0220, 34.7528)],
    "הרצליה":      [(32.1663, 34.8436), (32.1800, 34.8300)],
    "רעננה":       [(32.1838, 34.8705)],
    "כפר סבא":    [(32.1754, 34.9073)],
    "הוד השרון":   [(32.1525, 34.8955)],
    "נתניה":       [(32.3215, 34.8532), (32.3000, 34.8600)],
    "רחובות":      [(31.8928, 34.8113)],
    "נס ציונה":    [(31.9309, 34.7978)],
    "מודיעין":     [(31.8969, 35.0095)],
}

CITY_SLUG: dict[str, str] = {
    "תל אביב": "tel-aviv", "רמת גן": "ramat-gan", "גבעתיים": "givatayim",
    "בני ברק": "bnei-brak", "פתח תקווה": "petah-tikva", "ראשון לציון": "rishon-lezion",
    "חולון": "holon", "בת ים": "bat-yam", "הרצליה": "herzliya", "רעננה": "raanana",
    "כפר סבא": "kfar-saba", "הוד השרון": "hod-hasharon", "נתניה": "netanya",
    "רחובות": "rehovot", "נס ציונה": "nes-ziona", "מודיעין": "modiin",
}


def _normalize_name(s: str) -> str:
    """Lowercase, strip punctuation and common noise words for comparison."""
    s = s.lower()
    s = re.sub(r"[^\w\s֐-׿]", " ", s)
    noise = {"restaurant", "rest", "bar", "cafe", "kitchen", "tlv", "תל", "אביב", "מסעדת", "קפה"}
    tokens = [t for t in s.split() if t not in noise and len(t) > 1]
    return " ".join(tokens)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two lat/lon points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _name_similarity(a: str, b: str) -> float:
    """Rough token overlap ratio between 0 and 1."""
    na, nb = set(_normalize_name(a).split()), set(_normalize_name(b).split())
    if not na or not nb:
        return 0.0
    return len(na & nb) / max(len(na), len(nb))


async def fetch_wolt_venues(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    try:
        r = await client.get(
            WOLT_API,
            params={"lat": lat, "lon": lon},
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0",
                     "w-wolt-session-id": "reco-enrichment"},
        )
        r.raise_for_status()
        data = r.json()
        venues = []
        for section in data.get("sections", []):
            for item in section.get("items", []):
                v = item.get("venue")
                if isinstance(v, dict) and v.get("slug"):
                    venues.append(v)
        return venues
    except Exception as e:
        print(f"    Wolt fetch error ({lat},{lon}): {e}")
        return []


async def enrich():
    # 1. Load all our places from the DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Place).where(Place.lat.isnot(None), Place.lng.isnot(None)))
        places = list(result.scalars().all())
        # Track which places already have a wolt source
        existing = await db.execute(
            select(DataSource.place_id).where(DataSource.source_type == "wolt")
        )
        already_wolt = set(existing.scalars().all())

    places_needing_wolt = [p for p in places if p.id not in already_wolt]
    print(f"Matching {len(places_needing_wolt)} places against Wolt…")

    # 2. Collect all Wolt venues per city
    city_venues: dict[str, list[dict]] = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for city, coords_list in CITY_COORDS.items():
            seen_slugs: set[str] = set()
            venues: list[dict] = []
            for lat, lon in coords_list:
                batch = await fetch_wolt_venues(client, lat, lon)
                for v in batch:
                    if v["slug"] not in seen_slugs:
                        seen_slugs.add(v["slug"])
                        venues.append(v)
                await asyncio.sleep(0.3)
            city_venues[city] = venues
            print(f"  {city}: {len(venues)} Wolt venues found")

    # 3. Match each place to a Wolt venue
    matched = 0
    async with AsyncSessionLocal() as db:
        for place in places_needing_wolt:
            city = place.city or ""
            venues = city_venues.get(city, [])
            if not venues:
                continue

            best_venue = None
            best_score = 0.0

            for v in venues:
                loc = v.get("location", [])
                if len(loc) == 2:
                    vlon, vlat = loc[0], loc[1]
                    dist = _haversine_m(place.lat, place.lng, vlat, vlon)
                else:
                    dist = 9999

                name_sim = _name_similarity(place.name, v.get("name", ""))

                # Combined score: close distance + similar name
                dist_score = max(0.0, 1.0 - dist / 300)   # full score within 300m
                score = dist_score * 0.5 + name_sim * 0.5

                if score > best_score:
                    best_score = score
                    best_venue = v

            if best_venue and best_score >= 0.35:
                slug = best_venue["slug"]
                city_slug = CITY_SLUG.get(city, "tel-aviv")
                wolt_url = f"{WOLT_BASE}/{city_slug}/restaurant/{slug}"
                rating_info = best_venue.get("rating", {})
                excerpt = best_venue.get("short_description") or None

                source = DataSource(
                    place_id=place.id,
                    source_type="wolt",
                    source_name="Wolt",
                    url=wolt_url,
                    excerpt=excerpt,
                    review_count=rating_info.get("volume"),
                    confidence=min(best_score, 0.85),
                )
                db.add(source)
                matched += 1

        await db.commit()

    print(f"\n✓ Matched {matched} places to Wolt venues.")


if __name__ == "__main__":
    asyncio.run(enrich())
