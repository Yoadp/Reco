"""
Match our restaurants to Ontopo venues and add DataSource rows.
Fetches Ontopo city marketplace pages (no API key required) and extracts
venue cards (name + address) to match against our places by name similarity.

Usage:
    poetry run python -m app.workers.ontopo_enrichment
"""

import asyncio
import re
import httpx
import json
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

ONTOPO_BASE = "https://ontopo.com"

# Ontopo marketplace slugs for central Israel cities
CITY_SLUGS: dict[str, str] = {
    "תל אביב":     "tel-aviv",
    "חולון":       "holon",
    "בת ים":       "bat-yam",
    "גבעתיים":     "givatayim",
    "רמת גן":      "ramat-gan",
    "בני ברק":     "bnei-brak",
    "פתח תקווה":   "petah-tikva",
    "ראשון לציון": "rishon-lezion",
    "הרצליה":      "herzliya",
    "רעננה":       "raanana",
    "כפר סבא":     "kfar-saba",
    "הוד השרון":   "hod-hasharon",
    "נתניה":       "netanya",
    "רחובות":      "rehovot",
    "נס ציונה":    "nes-ziona",
    "מודיעין":     "modiin",
}


def _normalize(s: str) -> str:
    """Strip punctuation and noise words for comparison."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s֐-׿]", " ", s)
    noise = {"מסעדת", "מסעדה", "restaurant", "bar", "cafe", "kitchen", "tlv", "תל", "אביב"}
    tokens = [t for t in s.split() if t not in noise and len(t) > 1]
    return " ".join(tokens)


def _name_score(our_name: str, ontopo_name: str) -> float:
    a, b = set(_normalize(our_name).split()), set(_normalize(ontopo_name).split())
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def _extract_initial_state(html: str) -> dict:
    start = html.find("window.__INITIAL_STATE__=") + len("window.__INITIAL_STATE__=")
    if start < 30:
        return {}
    depth, end = 0, start
    for i, ch in enumerate(html[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth == 0 and i > start:
            end = i + 1
            break
    try:
        return json.loads(html[start:end])
    except Exception:
        return {}


def _extract_venue_cards(state: dict) -> list[dict]:
    """Pull all type='venue' cards from marketplace highlights."""
    venues = []
    try:
        highlights = (
            state.get("websiteContentStore", {})
            .get("marketplace", {})
            .get("highlights", [])
        )
        for section in highlights:
            for card in section.get("cards", []):
                if card.get("type") == "venue" and card.get("value"):
                    venues.append({
                        "id":      card["value"],
                        "name":    card.get("title", "").strip(),
                        "address": card.get("description", "").strip(),
                    })
    except Exception:
        pass
    return venues


async def fetch_city_venues(client: httpx.AsyncClient, city_slug: str) -> list[dict]:
    try:
        r = await client.get(
            f"{ONTOPO_BASE}/he/il/{city_slug}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        state = _extract_initial_state(r.text)
        return _extract_venue_cards(state)
    except Exception as e:
        print(f"  Ontopo fetch error for {city_slug}: {e}")
        return []


async def enrich():
    # Load our places
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Place))
        places = list(result.scalars().all())
        existing = await db.execute(
            select(DataSource.place_id).where(DataSource.source_type == "ontopo")
        )
        already_ontopo = set(existing.scalars().all())

    places_to_match = [p for p in places if p.id not in already_ontopo]
    print(f"Matching {len(places_to_match)} places against Ontopo…")

    # Fetch venue cards for all cities
    city_venues: dict[str, list[dict]] = {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for city_he, city_slug in CITY_SLUGS.items():
            venues = await fetch_city_venues(client, city_slug)
            city_venues[city_he] = venues
            print(f"  {city_he} ({city_slug}): {len(venues)} Ontopo venues")
            await asyncio.sleep(0.3)

    # Match each place
    matched = 0
    async with AsyncSessionLocal() as db:
        for place in places_to_match:
            city = place.city or ""
            # Try the exact city first, then all cities combined
            candidates = city_venues.get(city, [])
            if not candidates:
                for v in city_venues.values():
                    candidates.extend(v)

            best = None
            best_score = 0.0
            for v in candidates:
                score = _name_score(place.name, v["name"])
                if score > best_score:
                    best_score = score
                    best = v

            if best and best_score >= 0.5:
                city_slug = CITY_SLUGS.get(city, "tel-aviv")
                url = f"{ONTOPO_BASE}/he/il/{city_slug}/page/{best['id']}"
                source = DataSource(
                    place_id=place.id,
                    source_type="ontopo",
                    source_name="Ontopo",
                    url=url,
                    excerpt=best["address"] if best["address"] else None,
                    confidence=min(best_score, 0.85),
                )
                db.add(source)
                matched += 1

        await db.commit()

    print(f"\n✓ Matched {matched} places to Ontopo venues.")


if __name__ == "__main__":
    asyncio.run(enrich())
