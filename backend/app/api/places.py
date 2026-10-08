import asyncio
import re
import time
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.place import DataSource
from app.models.menu_item import MenuItem
from app.services.places import search_places, get_place_by_slug, smart_search_places

router = APIRouter(prefix="/places", tags=["places"])


class DataSourceOut(BaseModel):
    source_type: str
    source_name: str | None
    url: str | None
    excerpt: str | None
    review_count: int | None
    confidence: float
    scraped_at: datetime

    class Config:
        from_attributes = True


class PlaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    address: str | None
    city: str | None
    lat: float | None
    lng: float | None
    cuisine: List[str] | None
    price_range: int | None
    aggregated_score: float | None
    photos: List[str] | None
    phone: str | None
    website: str | None
    hours: dict | None
    matched_dishes: List[str] | None = None

    class Config:
        from_attributes = True


class PlaceDetailOut(PlaceOut):
    sources: List[DataSourceOut] = []


class ParsedQuery(BaseModel):
    dish: str | None
    cuisine: str | None
    price_min_ils: int | None
    price_max_ils: int | None
    city: str | None
    party_size: int | None = None
    open_at_day: int | None = None
    open_at_hour: int | None = None


class SmartSearchOut(BaseModel):
    exact: List[PlaceOut]
    similar: List[PlaceOut]
    parsed: ParsedQuery


# /places/smart must be registered BEFORE /{slug} to avoid route conflict
@router.get("/smart", response_model=SmartSearchOut)
async def smart_search(
    q: str = Query(..., min_length=1),
    city: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    result = await smart_search_places(db, q=q, city=city)
    return SmartSearchOut(
        exact=result["exact"],
        similar=result["similar"],
        parsed=ParsedQuery(**result["parsed"]),
    )


@router.get("", response_model=List[PlaceOut])
async def list_places(
    q: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    cuisine: Optional[str] = Query(None),
    price_range: Optional[int] = Query(None, ge=1, le=4),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    nlp: bool = Query(False),
    open_now: bool = Query(False),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(None),
    sort: Optional[str] = Query(None),
    open_at_day: Optional[int] = Query(None, ge=0, le=6),
    open_at_hour: Optional[int] = Query(None, ge=0, le=23),
    db: AsyncSession = Depends(get_db),
):
    open_at = (open_at_day, open_at_hour) if open_at_day is not None and open_at_hour is not None else None
    places, matched = await search_places(
        db, q=q, city=city, cuisine=cuisine, price_range=price_range,
        limit=limit, offset=offset, nlp=nlp,
        open_now=open_now, lat=lat, lng=lng, radius_km=radius_km, sort=sort,
        open_at=open_at,
    )
    out = []
    for p in places:
        item = PlaceOut.model_validate(p)
        dishes = matched.get(str(p.id))
        if dishes:
            item.matched_dishes = dishes
        out.append(item)
    return out


class MenuItemOut(BaseModel):
    id: uuid.UUID
    name: str
    price_ils: int | None
    description: str | None
    category: str | None
    source: str | None

    class Config:
        from_attributes = True


# ─── Availability (Ontopo real slots) ────────────────────────────────────────

# In-memory cache: key → (fetched_at_unix, slots_list)
_avail_cache: dict[str, tuple[float, list[str]]] = {}
_AVAIL_CACHE_TTL = 30 * 60  # 30 minutes

# Discovered URL cache: slug → url (None = searched but not found)
_url_discover_cache: dict[str, str | None] = {}

_INITIAL_STATE_RE = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{)')
_ONTOPO_VENUE_ID_RE = re.compile(r'/he/il/[^/]+/page/(\d+)')

# Hebrew city → Ontopo city slug
_ONTOPO_CITY_SLUGS: dict[str, str] = {
    "תל אביב":     "tel-aviv",
    "יפו":         "tel-aviv",
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
    "ירושלים":     "jerusalem",
    "חיפה":        "haifa",
    "באר שבע":     "beer-sheva",
}


def _normalize_name(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\sא-ת]", " ", s)
    noise = {"מסעדת", "מסעדה", "restaurant", "bar", "cafe", "kitchen", "tlv"}
    return " ".join(t for t in s.split() if t not in noise and len(t) > 1)


def _name_score(a: str, b: str) -> float:
    sa, sb = set(_normalize_name(a).split()), set(_normalize_name(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


async def _fetch_venue_name(client: httpx.AsyncClient, city_slug: str, venue_id: str) -> str | None:
    """Fetch one Ontopo venue page and return its name from pageData.title."""
    try:
        url = f"https://ontopo.com/he/il/{city_slug}/page/{venue_id}"
        r = await client.get(url, timeout=6.0)
        if r.status_code != 200:
            return None
        m = _INITIAL_STATE_RE.search(r.text)
        if not m:
            return None
        start = m.start(1)
        depth, end = 0, start
        for i, ch in enumerate(r.text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth == 0 and i > start:
                end = i + 1
                break
        import json as _json
        state = _json.loads(r.text[start:end])
        return state["websiteContentStore"]["pageData"]["title"]
    except Exception:
        return None


async def _discover_ontopo_url(slug: str, place_name: str, city: str | None) -> str | None:
    """Search Ontopo for a venue by name when the stored URL is stale.

    1. Check in-memory discovery cache first.
    2. Fetch the city listing page; try highlight cards (names available in SSR).
    3. Fall back to checking the first 20 venue IDs from page HTML in parallel.
    Caches the result (including misses) so each restaurant is searched at most once.
    """
    import json as _json

    if slug in _url_discover_cache:
        return _url_discover_cache[slug]

    city_slug = _ONTOPO_CITY_SLUGS.get(city or "")
    if not city_slug:
        _url_discover_cache[slug] = None
        return None

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            follow_redirects=True,
        ) as client:
            # Fetch city listing to get venue IDs from HTML links
            r = await client.get(f"https://ontopo.com/he/il/{city_slug}")
            if r.status_code != 200:
                _url_discover_cache[slug] = None
                return None

            venue_ids = list(dict.fromkeys(_ONTOPO_VENUE_ID_RE.findall(r.text)))[:20]
            if not venue_ids:
                _url_discover_cache[slug] = None
                return None

            # Fetch venue pages in parallel; only working pages return a name
            sem = asyncio.Semaphore(5)

            async def check(vid: str) -> tuple[str, str | None]:
                async with sem:
                    name = await _fetch_venue_name(client, city_slug, vid)
                    return vid, name

            results = await asyncio.gather(*[check(vid) for vid in venue_ids])
            best_score, best_vid = 0.0, None
            for vid, name in results:
                if name:
                    score = _name_score(place_name, name)
                    if score > best_score:
                        best_score, best_vid = score, vid

            if best_vid and best_score >= 0.45:
                found = f"https://ontopo.com/he/il/{city_slug}/page/{best_vid}"
                _url_discover_cache[slug] = found
                return found

    except Exception:
        pass

    _url_discover_cache[slug] = None
    return None


def _extract_ontopo_slots(html: str) -> list[str]:
    """Parse Ontopo venue page HTML for available time slots.

    Ontopo stores SSR state at window.__INITIAL_STATE__.
    Available times live at:
      websiteContentStore.pageShifts.items.time.options[]
        → {disabled: bool, option: {label: "17:30", value: "1730"}}
    """
    import json as _json

    m = _INITIAL_STATE_RE.search(html)
    if not m:
        return []
    start = m.start(1)
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
        state = _json.loads(html[start:end])
    except Exception:
        return []

    slots: list[str] = []

    # Primary path: pageShifts.items.time.options
    try:
        options = (
            state["websiteContentStore"]["pageShifts"]["items"]["time"]["options"]
        )
        for opt in options:
            if opt.get("disabled"):
                continue
            label = (opt.get("option") or {}).get("label") or ""
            if re.match(r'^\d{1,2}:\d{2}$', label):
                slots.append(label.zfill(5))
    except (KeyError, TypeError):
        pass

    # Fallback: walk the whole tree for any non-disabled time options
    if not slots:
        def _walk(obj, depth=0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                # pattern: {disabled: bool, option: {label: "HH:MM"}}
                if "disabled" in obj and not obj["disabled"]:
                    lbl = (obj.get("option") or {}).get("label") or ""
                    if re.match(r'^\d{1,2}:\d{2}$', lbl):
                        slots.append(lbl.zfill(5))
                for v in obj.values():
                    _walk(v, depth + 1)
            elif isinstance(obj, list):
                for v in obj:
                    _walk(v, depth + 1)
        _walk(state)

    return sorted(set(slots))


class AvailabilityOut(BaseModel):
    slots: list[str]
    source: str  # "ontopo" | "none"
    venue_url: str | None = None


@router.get("/{slug}/availability", response_model=AvailabilityOut)
async def get_place_availability(
    slug: str,
    party_size: int = Query(2, ge=1, le=20),
    target_date: Optional[str] = Query(None, alias="date"),  # YYYY-MM-DD
    db: AsyncSession = Depends(get_db),
):
    place = await get_place_by_slug(db, slug)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Find Ontopo source
    ontopo_source = next(
        (s for s in (place.sources or [])
         if s.source_type in ("ontopo", "menu") and s.url and "ontopo.com" in (s.url or "")),
        None
    )
    if not ontopo_source or not ontopo_source.url:
        return AvailabilityOut(slots=[], source="none")

    date_str = target_date or date.today().isoformat()
    cache_key = f"{slug}:{date_str}:{party_size}"

    # Return cached result if fresh
    if cache_key in _avail_cache:
        fetched_at, cached_slots = _avail_cache[cache_key]
        if time.time() - fetched_at < _AVAIL_CACHE_TTL:
            return AvailabilityOut(slots=cached_slots, source="ontopo", venue_url=ontopo_source.url)

    venue_url = ontopo_source.url
    got_valid_response = False  # only cache when we have a real venue response

    async def _fetch_slots(url: str) -> tuple[list[str], int]:
        async with httpx.AsyncClient(
            timeout=8.0,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            follow_redirects=True,
        ) as client:
            r = await client.get(url, params={"date": date_str, "guests": str(party_size)})
        return _extract_ontopo_slots(r.text), r.status_code

    slots: list[str] = []
    try:
        slots, status = await _fetch_slots(venue_url)

        if status == 200:
            # Good response — cache it (may have 0 slots if genuinely unavailable)
            got_valid_response = True
        else:
            # Stale URL (404) — search for current venue URL
            discovered = await _discover_ontopo_url(slug, place.name, place.city)
            if discovered and discovered != venue_url:
                venue_url = discovered
                try:
                    slots, status = await _fetch_slots(venue_url)
                    got_valid_response = (status == 200)
                except Exception:
                    pass
    except Exception:
        pass

    if got_valid_response:
        _avail_cache[cache_key] = (time.time(), slots)
    return AvailabilityOut(slots=slots, source="ontopo", venue_url=venue_url)


@router.get("/{slug}/menu", response_model=List[MenuItemOut])
async def get_place_menu(slug: str, db: AsyncSession = Depends(get_db)):
    place = await get_place_by_slug(db, slug)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    result = await db.execute(
        select(MenuItem)
        .where(MenuItem.place_id == place.id)
        .order_by(MenuItem.category, MenuItem.name)
    )
    return list(result.scalars().all())


@router.get("/{slug}", response_model=PlaceDetailOut)
async def get_place(slug: str, db: AsyncSession = Depends(get_db)):
    place = await get_place_by_slug(db, slug)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return place
