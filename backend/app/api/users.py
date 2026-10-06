import uuid
from typing import List
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

    class Config:
        from_attributes = True


class TransactionOut(BaseModel):
    id: uuid.UUID
    delta: int
    reason: str

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_current_user)):
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
