import re
import json
import httpx
import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.place import Place, DataSource
from app.models.menu_item import MenuItem

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"

_nlp_cache: dict[str, dict] = {}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _ils_to_price_range(min_ils: float | None, max_ils: float | None) -> int | None:
    if min_ils is None and max_ils is None:
        return None
    mid = ((min_ils or 0) + (max_ils or min_ils or 0)) / 2
    if mid < 55:
        return 1
    if mid < 100:
        return 2
    if mid < 180:
        return 3
    return 4


async def nlp_parse_query(q: str) -> dict:
    """
    Uses Groq to parse a freeform Hebrew restaurant search query.
    Returns {city, cuisine, dish, price_min_ils, price_max_ils}.
    Falls back gracefully on any error.
    """
    key = q.strip().lower()
    if key in _nlp_cache:
        return _nlp_cache[key]

    prompt = f"""אתה מנתח שאילתות חיפוש לאפליקציית מסעדות ישראלית.
נתח את השאילתה הבאה וחלץ את השדות הבאים:
- city: שם עיר בעברית אם מוזכר (כגון תל אביב, יפו, חיפה, רמת גן), אחרת null
- cuisine: קטגוריית מטבח רחבה (כגון איטלקי, יפני, ים תיכוני, בשר, ישראלי), אחרת null
- dish: שם מנה ספציפית או תיאור אוכל מפורט (כגון פסטה ברוטב לימון, המבורגר כפול, ראמן חריף), אחרת null — שים לב: dish יכול להכיל מספר מילים
- price_min_ils: המחיר המינימלי בשקלים כמספר שלם אם מוזכר טווח מחיר (כגון "60-80 שקל", "עד 100"), אחרת null
- price_max_ils: המחיר המקסימלי בשקלים כמספר שלם אם מוזכר טווח מחיר, אחרת null

החזר JSON בלבד ללא markdown:
{{"city":null,"cuisine":null,"dish":null,"price_min_ils":null,"price_max_ils":null}}

דוגמאות:
- "פסטה ברוטב לימון במחיר 60-80" → {{"city":null,"cuisine":"איטלקי","dish":"פסטה ברוטב לימון","price_min_ils":60,"price_max_ils":80}}
- "סושי ברמת גן עד 120 שקל" → {{"city":"רמת גן","cuisine":"יפני","dish":"סושי","price_min_ils":null,"price_max_ils":120}}
- "חומוס זול" → {{"city":null,"cuisine":"מזרח תיכוני","dish":"חומוס","price_min_ils":null,"price_max_ils":50}}

שאילתה: "{q}"
"""
    _groq_fail = {"city": None, "cuisine": None, "dish": None, "price_min_ils": None, "price_max_ils": None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                },
            )
        if resp.status_code == 429:
            # Rate-limited (background job consuming quota) — treat query as dish keyword
            return _groq_fail
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        _nlp_cache[key] = parsed
        if len(_nlp_cache) > 200:
            oldest = next(iter(_nlp_cache))
            del _nlp_cache[oldest]
        return parsed
    except Exception:
        return _groq_fail


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
    limit: int = 100,
    offset: int = 0,
    nlp: bool = False,
) -> List[Place]:
    stmt = select(Place)

    if q:
        if nlp:
            parsed = await nlp_parse_query(q)

            if parsed.get("city") and not city:
                city = parsed["city"]

            cuisine_term: Optional[str] = None
            if parsed.get("cuisine") and not cuisine:
                cuisine_term = parsed["cuisine"]

            # Use new ILS price fields if available, fall back to legacy integer price
            if not price_range:
                price_range = _ils_to_price_range(
                    parsed.get("price_min_ils"),
                    parsed.get("price_max_ils"),
                )
                if price_range is None and parsed.get("price"):
                    _price_map = {"cheap": 1, "זול": 1, "medium": 2, "בינוני": 2, "expensive": 3, "יקר": 3}
                    try:
                        price_range = int(parsed["price"])
                    except (ValueError, TypeError):
                        price_range = _price_map.get(str(parsed["price"]).lower())

            _stopwords = {"מקום", "מסעדה", "אוכל", "מקומי", "טוב", "כאן"}
            dish = parsed.get("dish") or ""
            term = ""
            if dish and dish.strip() not in _stopwords:
                term = dish

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


async def smart_search_places(
    db: AsyncSession,
    q: str,
    city: Optional[str] = None,
) -> dict:
    """
    Returns {"exact": [...], "similar": [...], "parsed": {...}}.
    Cascades from strict to relaxed criteria to ensure results are always returned.
    """
    parsed = await nlp_parse_query(q)

    resolved_city = city or parsed.get("city")
    cuisine = parsed.get("cuisine")
    dish = parsed.get("dish")
    price_range = _ils_to_price_range(parsed.get("price_min_ils"), parsed.get("price_max_ils"))

    exact: List[Place] = []
    similar: List[Place] = []
    seen_ids: set[uuid.UUID] = set()

    def _add_to(bucket: List[Place], places: List[Place]) -> None:
        for p in places:
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                bucket.append(p)

    groq_failed = not dish and not cuisine and not resolved_city and not price_range

    if groq_failed:
        # Groq was rate-limited or failed — use raw query as keyword search directly
        fallback = await _search_with_excerpt(db, q, city, price_range=None, limit=20)
        _add_to(exact, fallback)
        # Also try plain ILIKE on name/cuisine
        if len(exact) < 5:
            plain = await search_places(db, q=q, city=city, limit=20)
            _add_to(exact, plain)
    else:
        # --- Tier 1: dish keyword + price_range + city (exact) ---
        if dish:
            tier1 = await _search_with_excerpt(db, dish, resolved_city, price_range, limit=20)
            _add_to(exact, tier1)

        # --- Tier 1.5: dish keyword in menu/reviews, any price (similar) ---
        if dish:
            tier1_any = await _search_with_excerpt(db, dish, resolved_city, price_range=None, limit=20)
            _add_to(similar, tier1_any)

        # --- Tier 2: cuisine + price_range + city ---
        if len(exact) < 3 and cuisine:
            tier2 = await search_places(db, q=cuisine, city=resolved_city, price_range=price_range, limit=20)
            _add_to(similar if exact else exact, tier2)

        # --- Tier 3: cuisine + city (no price) ---
        if len(exact) + len(similar) < 3 and cuisine:
            tier3 = await search_places(db, q=cuisine, city=resolved_city, limit=20)
            _add_to(similar, tier3)

        # --- Tier 4: city fallback or top-rated ---
        if len(exact) + len(similar) < 3:
            tier4 = await search_places(db, city=resolved_city, limit=20)
            if not tier4 and resolved_city:
                tier4 = await search_places(db, limit=20)
            _add_to(similar, tier4)

    return {
        "exact": exact,
        "similar": similar,
        "parsed": {
            "dish": dish if not groq_failed else q,
            "cuisine": cuisine,
            "price_min_ils": parsed.get("price_min_ils"),
            "price_max_ils": parsed.get("price_max_ils"),
            "city": resolved_city,
        },
    }


async def _search_with_excerpt(
    db: AsyncSession,
    keyword: str,
    city: Optional[str],
    price_range: Optional[int],
    limit: int = 20,
) -> List[Place]:
    """Search Place name/cuisine, DataSource excerpts, AND menu_items for a keyword."""
    # Build word list: search all significant words from the keyword individually
    words = [w for w in keyword.split() if len(w) >= 3]
    # Always include the full keyword too
    search_terms = list(dict.fromkeys([keyword] + words))  # deduplicate while preserving order

    conditions = [
        Place.name.ilike(f"%{keyword}%"),
        func.array_to_string(Place.cuisine, " ").ilike(f"%{keyword}%"),
    ]

    # Subquery: place IDs whose review/menu excerpts mention any search term
    excerpt_conditions = [DataSource.excerpt.ilike(f"%{t}%") for t in search_terms]
    excerpt_subq = (
        select(DataSource.place_id)
        .where(or_(*excerpt_conditions))
        .scalar_subquery()
    )
    conditions.append(Place.id.in_(excerpt_subq))

    # Subquery: place IDs whose menu item names OR categories match any search term.
    # Also add prefix variants (e.g. "פסטה" → "פסט" to catch "פסטות", "פסטות" etc.)
    menu_conditions = []
    for t in search_terms:
        menu_conditions.append(MenuItem.name.ilike(f"%{t}%"))
        menu_conditions.append(MenuItem.category.ilike(f"%{t}%"))
        if len(t) >= 4:
            # stem match (drop last letter): פסטה→פסט, פיצה→פיצ catches פסטות/פיצות
            stem = t[:-1]
            menu_conditions.append(MenuItem.category.ilike(f"{stem}%"))
    menu_subq = (
        select(MenuItem.place_id)
        .where(or_(*menu_conditions))
        .scalar_subquery()
    )
    conditions.append(Place.id.in_(menu_subq))

    stmt = select(Place).where(or_(*conditions))

    if city:
        stmt = stmt.where(
            or_(Place.city.ilike(f"%{city}%"), Place.address.ilike(f"%{city}%"))
        )
    if price_range:
        stmt = stmt.where(Place.price_range == price_range)

    stmt = stmt.order_by(Place.aggregated_score.desc().nulls_last()).limit(limit)
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
    if data.get("cuisine") and not place.cuisine:
        place.cuisine = data["cuisine"]

    await db.flush()
    return place
