import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.recommendation import PointsTransaction

router = APIRouter(prefix="/users", tags=["users"])


class UserProfile(BaseModel):
    id: uuid.UUID
    username: str
    points_balance: int
    tier: str
    cuisine_preferences: List[str] | None = None
    dietary_restrictions: List[str] | None = None
    price_preference: int | None = None

    class Config:
        from_attributes = True


class UpdatePreferences(BaseModel):
    cuisine_preferences: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    price_preference: Optional[int] = None


class TransactionOut(BaseModel):
    id: uuid.UUID
    delta: int
    reason: str

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me/preferences", response_model=UserProfile)
async def update_preferences(
    body: UpdatePreferences,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.cuisine_preferences is not None:
        user.cuisine_preferences = body.cuisine_preferences
    if body.dietary_restrictions is not None:
        user.dietary_restrictions = body.dietary_restrictions
    if body.price_preference is not None:
        user.price_preference = body.price_preference
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me/transactions", response_model=List[TransactionOut])
async def get_my_transactions(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PointsTransaction)
        .where(PointsTransaction.user_id == user.id)
        .order_by(PointsTransaction.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
