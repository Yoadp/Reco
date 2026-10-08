import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.saved_place import SavedPlace
from app.models.place import Place

router = APIRouter(prefix="/saved", tags=["saved"])


class SaveRequest(BaseModel):
    place_id: uuid.UUID
    list_type: str = "wishlist"  # "wishlist" | "favorite"


class SavedPlaceOut(BaseModel):
    id: uuid.UUID
    place_id: uuid.UUID
    list_type: str

    class Config:
        from_attributes = True


class SavedPlaceWithPlace(BaseModel):
    id: uuid.UUID
    place_id: uuid.UUID
    list_type: str
    place: dict

    class Config:
        from_attributes = True


@router.post("", response_model=SavedPlaceOut)
async def save_place(
    body: SaveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check place exists
    place = await db.get(Place, body.place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Upsert: check if already saved
    existing = await db.execute(
        select(SavedPlace).where(
            SavedPlace.user_id == user.id,
            SavedPlace.place_id == body.place_id,
            SavedPlace.list_type == body.list_type,
        )
    )
    saved = existing.scalar_one_or_none()
    if saved:
        return saved

    saved = SavedPlace(user_id=user.id, place_id=body.place_id, list_type=body.list_type)
    db.add(saved)
    await db.commit()
    await db.refresh(saved)
    return saved


@router.delete("/{place_id}")
async def unsave_place(
    place_id: uuid.UUID,
    list_type: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = delete(SavedPlace).where(
        SavedPlace.user_id == user.id,
        SavedPlace.place_id == place_id,
    )
    if list_type:
        stmt = stmt.where(SavedPlace.list_type == list_type)
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}


@router.get("", response_model=List[SavedPlaceOut])
async def get_saved(
    list_type: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SavedPlace).where(SavedPlace.user_id == user.id)
    if list_type:
        stmt = stmt.where(SavedPlace.list_type == list_type)
    stmt = stmt.order_by(SavedPlace.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/places", response_model=List[dict])
async def get_saved_with_places(
    list_type: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns saved places with full place data."""
    stmt = select(SavedPlace).where(SavedPlace.user_id == user.id)
    if list_type:
        stmt = stmt.where(SavedPlace.list_type == list_type)
    stmt = stmt.order_by(SavedPlace.created_at.desc())
    result = await db.execute(stmt)
    saved_rows = list(result.scalars().all())

    place_ids = [s.place_id for s in saved_rows]
    if not place_ids:
        return []

    places_result = await db.execute(select(Place).where(Place.id.in_(place_ids)))
    places_map = {p.id: p for p in places_result.scalars().all()}

    output = []
    for s in saved_rows:
        p = places_map.get(s.place_id)
        if p:
            output.append({
                "saved_id": str(s.id),
                "list_type": s.list_type,
                "id": str(p.id),
                "name": p.name,
                "slug": p.slug,
                "address": p.address,
                "city": p.city,
                "lat": p.lat,
                "lng": p.lng,
                "cuisine": p.cuisine,
                "price_range": p.price_range,
                "aggregated_score": p.aggregated_score,
                "photos": p.photos,
                "phone": p.phone,
                "website": p.website,
                "hours": p.hours,
            })
    return output
