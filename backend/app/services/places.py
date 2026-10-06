import re
import json
import httpx
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.place import Place

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"

_nlp_cache: dict[str, dict] = {}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def nlp_parse_query(q: str) -> dict:
    """
    Uses Groq to parse a freeform Hebrew restaurant search query.
    Returns {"city": str|None, "cuisine": str|None, "price": int|None, "term": str|None}.
    Falls back to {"term": q} on any error so search always works.
    """
    key = q.strip().lower()
    if key in _nlp_cache:
        return _nlp_cache[key]

    prompt = f"""אתה מנתח שאילתות חיפוש לאפליקציית מסעדות ישראלית.
נתח את השאילתה הבאה וחלץ:
- city: שם עיר בעברית אם מוזכר (כגון תל אביב, יפו, ירושלים, חיפה, רמת גן וכו׳), אחרת null
- cuisine: סוג מטבח או מאכל (כגון פסטה, סושי, חומוס, פיצה, בשר, איטלקי, יפני), אחרת null
- price: 1=זול/במחיר סביר, 2=בינוני, 3=יקר, 4=יקר מאוד, null אם לא מוזכר תקציב
- term: שאר הטקסט שלא נכלל לעיל (כגון שם מסעדה ספציפי או ביטוי חופשי), null אם אין

החזר JSON בלבד ללא markdown:
{{"city":null,"cuisine":null,"price":null,"term":null}}

שאילתה: "{q}"
"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                },
            )
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        _nlp_cache[key] = parsed
        if len(_nlp_cache) > 200:
            oldest = next(iter(_nlp_cache))
            del _nlp_cache[oldest]
        return parsed
    except Exception:
        return {"city": None, "cuisine": None, "price": None, "term": q}


async def get_place_by_slug(db: AsyncSession, slug: str) -> Optional[Place]:
    result = await db.execute(
        select(Place).where(Place.slug == slug).options(selectinload(Place.sources))
    )
    return result.scalar_one_or_none()


async def search_places(
    db: AsyncSession,
    q: Optional[str] = None,
    city: Optional[str] = None,
    cuisine: Optional[str] = None,
    price_range: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
    nlp: bool = False,
) -> List[Place]:
    stmt = select(Place)

    if q:
        if nlp:
            # --- NLP path: ask Groq to parse freeform Hebrew query ---
            parsed = await nlp_parse_query(q)

            if parsed.get("city") and not city:
                city = parsed["city"]

            cuisine_term: Optional[str] = None
            if parsed.get("cuisine") and not cuisine:
                cuisine_term = parsed["cuisine"]

            raw_price = parsed.get("price")
            if raw_price and not price_range:
                _price_map = {"cheap": 1, "זול": 1, "medium": 2, "בינוני": 2, "expensive": 3, "יקר": 3}
                try:
                    price_range = int(raw_price)
                except (ValueError, TypeError):
                    price_range = _price_map.get(str(raw_price).lower())

            _stopwords = {"מקום", "מסעדה", "אוכל", "מקומי", "טוב", "כאן"}
            term = parsed.get("term") or ""
            if term.strip() in _stopwords:
                term = ""

            if term or cuisine_term:
                conditions = []
                if term:
                    conditions += [
                        Place.name.ilike(f"%{term}%"),
                        Place.address.ilike(f"%{term}%"),
                        func.array_to_string(Place.cuisine, " ").ilike(f"%{term}%"),
                    ]
                if cuisine_term:
                    conditions += [
                        func.array_to_string(Place.cuisine, " ").ilike(f"%{cuisine_term}%"),
                        Place.name.ilike(f"%{cuisine_term}%"),
                    ]
                stmt = stmt.where(or_(*conditions))
        else:
            # --- Fast path: plain ILIKE on name, address, cuisine ---
            stmt = stmt.where(
                or_(
                    Place.name.ilike(f"%{q}%"),
                    Place.address.ilike(f"%{q}%"),
                    func.array_to_string(Place.cuisine, " ").ilike(f"%{q}%"),
                )
            )

    if city:
        stmt = stmt.where(
            or_(
                Place.city.ilike(f"%{city}%"),
                Place.address.ilike(f"%{city}%"),
            )
        )
    if cuisine:
        stmt = stmt.where(Place.cuisine.any(cuisine))
    if price_range:
        stmt = stmt.where(Place.price_range == price_range)

    stmt = stmt.order_by(Place.aggregated_score.desc().nulls_last()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def upsert_place_from_google(db: AsyncSession, data: dict) -> Place:
    """Insert or update a place from a Google Places API response dict."""
    result = await db.execute(select(Place).where(Place.google_place_id == data["place_id"]))
    place = result.scalar_one_or_none()

    base_slug = slugify(data["name"])
    if place is None:
        slug = base_slug
        count = 0
        while True:
            existing = await db.execute(select(Place).where(Place.slug == slug))
            if existing.scalar_one_or_none() is None:
                break
            count += 1
            slug = f"{base_slug}-{count}"

        place = Place(
            name=data["name"],
            slug=slug,
            google_place_id=data["place_id"],
            city=data.get("city", ""),
        )
        db.add(place)

    place.address = data.get("formatted_address", place.address)
    place.lat = data.get("lat", place.lat)
    place.lng = data.get("lng", place.lng)
    place.phone = data.get("formatted_phone_number", place.phone)
    place.website = data.get("website", place.website)
    place.hours = data.get("opening_hours", place.hours)
    place.photos = data.get("photos", place.photos)
    place.aggregated_score = data.get("rating", place.aggregated_score)

    await db.flush()
    return place
