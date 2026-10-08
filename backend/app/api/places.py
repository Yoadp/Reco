import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    db: AsyncSession = Depends(get_db),
):
    places, matched = await search_places(
        db, q=q, city=city, cuisine=cuisine, price_range=price_range,
        limit=limit, offset=offset, nlp=nlp,
        open_now=open_now, lat=lat, lng=lng, radius_km=radius_km, sort=sort,
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
