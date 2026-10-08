import re
import json
import math
import httpx
import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Path where real-query training examples are appended
_TRAINING_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "real_queries.jsonl"
_training_seen: set[str] = set()  # deduplicate within a process lifetime


def _save_training_example(query: str, result: dict) -> None:
    """Append a (query, groq_result) pair to the real-queries training file.
    Fire-and-forget — never raises, never blocks the caller."""
    key = query.strip().lower()
    if key in _training_seen:
        return
    _training_seen.add(key)
    try:
        _TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"input": query, "output": json.dumps(result, ensure_ascii=False)},
            ensure_ascii=False,
        )
        with open(_TRAINING_DATA_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:
        logger.debug("Could not save training example: %s", exc)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.place import Place, DataSource
from app.models.menu_item import MenuItem
from app.models.rating import PlaceRating

# Hebrew ו (and) attaches directly to next word: "פאד תאי וסלט" not "פאד תאי ו סלט"
# Pattern: 1+ spaces before ו, then optional spaces (ו may or may not have space after)
_DISH_SPLIT_RE = re.compile(r'\s+ו\s*|\s*,\s*|\s+and\s+', re.IGNORECASE)


def _split_dishes(q: str) -> list[str]:
    """Split compound queries like 'פאד תאי וסלט פאפאיה' into ['פאד תאי', 'סלט פאפאיה']."""
    parts = _DISH_SPLIT_RE.split(q)
    return [p.strip() for p in parts if len(p.strip()) >= 2]


def _menu_match_subq(term: str):
    """Subquery returning place_ids where any menu item name matches term."""
    return select(MenuItem.place_id).where(
        MenuItem.name.ilike(f"%{term}%")
    ).scalar_subquery()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

_nlp_cache: dict[str, dict] = {}

# Ordered longest-first so "תל אביב" is matched before "אביב"
_KNOWN_CITIES = sorted([
    "תל אביב", "יפו", "חיפה", "ירושלים", "באר שבע", "נתניה", "פתח תקווה",
    "ראשון לציון", "אשדוד", "חולון", "בני ברק", "רמת גן", "גבעתיים",
    "הרצליה", "רעננה", "כפר סבא", "הוד השרון", "מודיעין", "נס ציונה",
    "רחובות", "בת ים", "רמת השרון", "לוד", "רמלה", "אשקלון", "אילת",
    "עכו", "נהריה", "כפר יונה", "טירת כרמל", "קריית גת", "קריית ביאליק",
    "קריית ים", "קריית מוצקין", "קריית אתא", "אור יהודה", "גבעת שמואל",
], key=len, reverse=True)

_PRICE_KEYWORDS = {
    "זול": (None, 50), "זולה": (None, 50), "זולים": (None, 50),
    "יקר": (120, None), "יקרה": (120, None), "יוקרתי": (200, None),
    "בינוני": (60, 120), "בינונית": (60, 120),
}


def _local_parse_query(q: str) -> dict:
    """
    Best-effort local parse without Groq.
    Detects city names and simple price keywords from the query text.
    """
    result: dict = {"city": None, "cuisine": None, "dish": None, "price_min_ils": None, "price_max_ils": None}
    remaining = q

    # City detection
    for city in _KNOWN_CITIES:
        if city in q:
            result["city"] = city
            # Remove the city and the Hebrew "ב" preposition that precedes it ("ב" = "in")
            remaining = q.replace(city, "").strip()
            remaining = re.sub(r'\bב$', '', remaining).strip()   # trailing "ב " before city
            remaining = re.sub(r'^ב\b', '', remaining).strip()   # leading "ב" after city
            remaining = re.sub(r'\s+', ' ', remaining).strip()
            break

    # Price detection
    for word, (pmin, pmax) in _PRICE_KEYWORDS.items():
        if word in remaining:
            result["price_min_ils"] = pmin
            result["price_max_ils"] = pmax
            remaining = remaining.replace(word, "").strip()
            break

    # Whatever remains is treated as the dish/food term
    if remaining and len(remaining) >= 2:
        result["dish"] = remaining

    return result


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


def is_open_now(hours_json: dict | None) -> bool:
    """Check if a place is currently open based on Google's regularOpeningHours JSON."""
    if not hours_json or "periods" not in hours_json:
        return False

    now = datetime.now(ISRAEL_TZ)
    # Python weekday(): 0=Mon … 6=Sun → Google: 0=Sun, 1=Mon … 6=Sat
    google_day = (now.weekday() + 1) % 7
    current_mins = now.hour * 60 + now.minute

    for period in hours_json["periods"]:
        open_info = period.get("open", {})
        open_day = open_info.get("day")
        open_mins = open_info.get("hour", 0) * 60 + open_info.get("minute", 0)

        close_info = period.get("close")
        if close_info is None:
            return True  # 24/7

        close_day = close_info.get("day")
        close_mins = close_info.get("hour", 0) * 60 + close_info.get("minute", 0)

        if open_day == close_day:
            if google_day == open_day and open_mins <= current_mins < close_mins:
                return True
        else:
            # Spans midnight
            if google_day == open_day and current_mins >= open_mins:
                return True
            if google_day == close_day and current_mins < close_mins:
                return True

    return False


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Returns distance in km between two lat/lng points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


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
            # Rate-limited — try local model first, then regex fallback
            from app.ml.inference import local_model_parse
            return local_model_parse(q) or _local_parse_query(q)
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        _nlp_cache[key] = parsed
        if len(_nlp_cache) > 200:
            oldest = next(iter(_nlp_cache))
            del _nlp_cache[oldest]
        # Teach the local model with every real Groq answer
        asyncio.get_event_loop().run_in_executor(None, _save_training_example, q, parsed)
        return parsed
    except Exception:
        from app.ml.inference import local_model_parse
        return local_model_parse(q) or _local_parse_query(q)


async def get_place_by_slug(db: AsyncSession, slug: str) -> Optional[Place]:
    result = await db.execute(
        select(Place).where(Place.slug == slug).options(selectinload(Place.sources))
    )
    return result.scalar_one_or_none()


async def _trending_places(db: AsyncSession, limit: int = 8) -> List[Place]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    subq = (
        select(PlaceRating.place_id, func.count(PlaceRating.id).label("cnt"))
        .where(PlaceRating.created_at >= cutoff)
        .group_by(PlaceRating.place_id)
        .subquery()
    )
    stmt = (
        select(Place)
        .join(subq, Place.id == subq.c.place_id)
        .order_by(subq.c.cnt.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    places = list(result.scalars().all())
    # If not enough recent activity, fill with top-rated
    if len(places) < limit:
        existing_ids = {p.id for p in places}
        fill_stmt = (
            select(Place)
            .where(Place.id.not_in(existing_ids) if existing_ids else True)
            .order_by(Place.aggregated_score.desc().nulls_last())
            .limit(limit - len(places))
        )
        fill_result = await db.execute(fill_stmt)
        places += list(fill_result.scalars().all())
    return places


async def _hidden_gem_places(db: AsyncSession, limit: int = 8) -> List[Place]:
    source_count_subq = (
        select(func.count(DataSource.id))
        .where(DataSource.place_id == Place.id)
        .correlate(Place)
        .scalar_subquery()
    )
    stmt = (
        select(Place)
        .where(Place.aggregated_score >= 4.3)
        .where(source_count_subq <= 2)
        .order_by(Place.aggregated_score.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def search_places(
    db: AsyncSession,
    q: Optional[str] = None,
    city: Optional[str] = None,
    cuisine: Optional[str] = None,
    price_range: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    nlp: bool = False,
    open_now: bool = False,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    sort: Optional[str] = None,
) -> tuple[List[Place], dict[str, list[str]]]:
    # Discovery sort modes bypass regular search — return (places, {}) tuple
    if sort == "trending":
        return await _trending_places(db, limit=limit), {}
    if sort == "hidden_gems":
        return await _hidden_gem_places(db, limit=limit), {}
    if sort == "new":
        stmt = select(Place).order_by(Place.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all()), {}

    # When post-processing is needed, fetch more rows
    needs_postprocess = open_now or (lat is not None and lng is not None)
    fetch_limit = limit * 6 if needs_postprocess else limit

    stmt = select(Place)
    search_terms: list[str] = []  # dish terms extracted for matched_dishes post-query

    if q:
        if nlp:
            parsed = await nlp_parse_query(q)

            if parsed.get("city") and not city:
                city = parsed["city"]

            cuisine_term: Optional[str] = None
            if parsed.get("cuisine") and not cuisine:
                cuisine_term = parsed["cuisine"]

            # NLP-derived price: don't apply as hard SQL filter in search_places —
            # 96% of places have price_range=NULL so a hard AND kills most results.
            # smart_search_places() handles price with its cascade tiers instead.
            _nlp_price_range: Optional[int] = None
            if not price_range:
                _nlp_price_range = _ils_to_price_range(
                    parsed.get("price_min_ils"),
                    parsed.get("price_max_ils"),
                )

            _stopwords = {"מקום", "מסעדה", "אוכל", "מקומי", "טוב", "כאן"}
            dish = parsed.get("dish") or ""
            term = ""
            if dish and dish.strip() not in _stopwords:
                term = dish

            if term:
                search_terms = _split_dishes(term) or [term]
            # Bug 1 fix: Groq sometimes returns the whole compound phrase as one dish token.
            # If we still have only 1 term, try splitting the original query directly.
            if len(search_terms) <= 1:
                q_split = _split_dishes(q)
                if len(q_split) > 1:
                    search_terms = q_split
            if not search_terms and q:
                search_terms = [q]

            if search_terms or cuisine_term:
                if len(search_terms) > 1:
                    # Multi-dish: require ALL terms to match (AND)
                    for t in search_terms:
                        stmt = stmt.where(or_(
                            Place.name.ilike(f"%{t}%"),
                            func.array_to_string(Place.cuisine, " ").ilike(f"%{t}%"),
                            Place.id.in_(_menu_match_subq(t)),
                        ))
                else:
                    conditions = []
                    if search_terms:
                        t = search_terms[0]
                        conditions += [
                            Place.name.ilike(f"%{t}%"),
                            Place.address.ilike(f"%{t}%"),
                            func.array_to_string(Place.cuisine, " ").ilike(f"%{t}%"),
                            Place.id.in_(_menu_match_subq(t)),
                        ]
                    if cuisine_term:
                        conditions += [
                            func.array_to_string(Place.cuisine, " ").ilike(f"%{cuisine_term}%"),
                            Place.name.ilike(f"%{cuisine_term}%"),
                        ]
                    if conditions:
                        stmt = stmt.where(or_(*conditions))
        else:
            # Fast typing path: local parser extracts city & dish, no API call
            local = _local_parse_query(q)
            raw_term = local.get("dish") or q
            if local.get("city") and not city:
                city = local["city"]
            if local.get("price_min_ils") and not price_range:
                price_range = _ils_to_price_range(local["price_min_ils"], local.get("price_max_ils"))

            search_terms = _split_dishes(raw_term) or [raw_term]

            if len(search_terms) > 1:
                # Multi-dish: require ALL terms (AND across subqueries)
                for t in search_terms:
                    stmt = stmt.where(or_(
                        Place.name.ilike(f"%{t}%"),
                        func.array_to_string(Place.cuisine, " ").ilike(f"%{t}%"),
                        Place.id.in_(_menu_match_subq(t)),
                    ))
            else:
                t = search_terms[0]
                stmt = stmt.where(or_(
                    Place.name.ilike(f"%{t}%"),
                    Place.address.ilike(f"%{t}%"),
                    func.array_to_string(Place.cuisine, " ").ilike(f"%{t}%"),
                    Place.id.in_(_menu_match_subq(t)),
                ))

    if city:
        stmt = stmt.where(
            or_(
                Place.city.ilike(f"%{city}%"),
                Place.address.ilike(f"%{city}%"),
            )
        )
    if cuisine:
        stmt = stmt.where(Place.cuisine.any(cuisine))
    # Only apply price_range when it came in as a direct query param (not NLP-derived).
    # NLP-derived price is handled by smart_search_places() cascade tiers.
    if price_range:
        stmt = stmt.where(Place.price_range == price_range)

    stmt = stmt.order_by(Place.aggregated_score.desc().nulls_last()).limit(fetch_limit).offset(offset)
    result = await db.execute(stmt)
    places = list(result.scalars().all())

    # Post-process: open_now filter
    if open_now:
        places = [p for p in places if p.hours and is_open_now(p.hours)]

    # Post-process: distance sort/filter
    if lat is not None and lng is not None:
        with_dist = []
        for p in places:
            if p.lat and p.lng:
                d = haversine(lat, lng, p.lat, p.lng)
                if radius_km is None or d <= radius_km:
                    with_dist.append((p, d))
        with_dist.sort(key=lambda x: x[1])
        places = [p for p, _ in with_dist]

    places = places[:limit]

    # Build matched_dishes map: str(place_id) → list of matching menu item names
    matched: dict[str, list[str]] = {}
    if search_terms and places:
        for term in search_terms:
            mi_result = await db.execute(
                select(MenuItem.place_id, MenuItem.name)
                .where(MenuItem.place_id.in_([p.id for p in places]))
                .where(MenuItem.name.ilike(f"%{term}%"))
                .limit(500)
            )
            for place_id, item_name in mi_result.all():
                key = str(place_id)
                if key not in matched:
                    matched[key] = []
                if item_name not in matched[key]:
                    matched[key].append(item_name)

    return places, matched


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
            plain, _ = await search_places(db, q=q, city=city, limit=20)
            _add_to(exact, plain)
    else:
        # Location-first cascade: when a city is known, it is a hard constraint.
        # Food narrows results within the city; we never escape to other cities.

        # --- Tier 1: city + dish + price (exact food match in location) ---
        if dish:
            tier1 = await _search_with_excerpt(db, dish, resolved_city, price_range, limit=20)
            _add_to(exact, tier1)

        # --- Tier 2: city + dish (relax price) ---
        if dish:
            tier2 = await _search_with_excerpt(db, dish, resolved_city, price_range=None, limit=20)
            _add_to(exact if not exact else similar, tier2)

        # --- Tier 3: city + cuisine (broader food category) ---
        if cuisine:
            tier3, _ = await search_places(db, q=cuisine, city=resolved_city, price_range=price_range, limit=20)
            _add_to(similar, tier3)

        # --- Tier 4: city + cuisine (relax price) ---
        if cuisine:
            tier4, _ = await search_places(db, q=cuisine, city=resolved_city, limit=20)
            _add_to(similar, tier4)

        # --- Tier 5: city only (top rated in location) ---
        # Used when food results are thin. City constraint is kept — never escape.
        if len(exact) + len(similar) < 5:
            tier5, _ = await search_places(db, city=resolved_city, limit=20)
            _add_to(similar, tier5)

        # --- Tier 6: no city was specified — global food search as last resort ---
        if len(exact) + len(similar) < 3 and not resolved_city:
            tier6, _ = await search_places(db, q=dish or cuisine, limit=20)
            _add_to(similar, tier6)

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
    words = [w for w in keyword.split() if len(w) >= 3]
    search_terms = list(dict.fromkeys([keyword] + words))

    conditions = [
        Place.name.ilike(f"%{keyword}%"),
        func.array_to_string(Place.cuisine, " ").ilike(f"%{keyword}%"),
    ]

    excerpt_conditions = [DataSource.excerpt.ilike(f"%{t}%") for t in search_terms]
    excerpt_subq = (
        select(DataSource.place_id)
        .where(or_(*excerpt_conditions))
        .scalar_subquery()
    )
    conditions.append(Place.id.in_(excerpt_subq))

    menu_conditions = []
    for t in search_terms:
        menu_conditions.append(MenuItem.name.ilike(f"%{t}%"))
        menu_conditions.append(MenuItem.category.ilike(f"%{t}%"))
        if len(t) >= 4:
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
