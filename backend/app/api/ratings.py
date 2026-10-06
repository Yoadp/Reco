"""
Visit ratings — users score a restaurant 1-10 after visiting.
One rating per user per place (upsert on re-submit).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, bearer
from app.core.database import get_db
from app.models.rating import PlaceRating
from app.models.user import User
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(prefix="/ratings", tags=["ratings"])


class RateRequest(BaseModel):
    place_id: uuid.UUID
    score: int = Field(..., ge=1, le=10)


class PlaceRatingOut(BaseModel):
    avg_score: float | None
    count: int
    user_score: int | None


@router.post("", status_code=204)
async def rate_place(
    body: RateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        pg_insert(PlaceRating)
        .values(
            id=uuid.uuid4(),
            user_id=current_user.id,
            place_id=body.place_id,
            score=body.score,
        )
        .on_conflict_do_update(
            constraint="uq_user_place_rating",
            set_={"score": body.score},
        )
    )
    await db.execute(stmt)
    await db.commit()


@router.get("/place/{place_id}", response_model=PlaceRatingOut)
async def get_place_rating(
    place_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
):
    # Community average + count
    result = await db.execute(
        select(func.avg(PlaceRating.score), func.count(PlaceRating.id))
        .where(PlaceRating.place_id == place_id)
    )
    avg, count = result.one()

    user_score: int | None = None
    if credentials:
        from app.core.security import decode_token
        user_id = decode_token(credentials.credentials)
        if user_id:
            r = await db.execute(
                select(PlaceRating.score)
                .where(PlaceRating.place_id == place_id, PlaceRating.user_id == user_id)
            )
            row = r.scalar_one_or_none()
            if row is not None:
                user_score = int(row)

    return PlaceRatingOut(
        avg_score=round(float(avg), 1) if avg else None,
        count=count or 0,
        user_score=user_score,
    )
