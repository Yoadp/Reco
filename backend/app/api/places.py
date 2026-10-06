import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.places import search_places, get_place_by_slug

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

    class Config:
        from_attributes = True


class PlaceDetailOut(PlaceOut):
    sources: List[DataSourceOut] = []


@router.get("", response_model=List[PlaceOut])
async def list_places(
    q: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    cuisine: Optional[str] = Query(None),
    price_range: Optional[int] = Query(None, ge=1, le=4),
    limit: int = Query(20, le=50),
    offset: int = Query(0),
    nlp: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    return await search_places(db, q=q, city=city, cuisine=cuisine, price_range=price_range, limit=limit, offset=offset, nlp=nlp)


@router.get("/{slug}", response_model=PlaceDetailOut)
async def get_place(slug: str, db: AsyncSession = Depends(get_db)):
    place = await get_place_by_slug(db, slug)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return place
