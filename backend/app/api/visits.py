import uuid
from datetime import date as date_type, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.visit import UserVisit

router = APIRouter(prefix="/visits", tags=["visits"])


class CreateVisitRequest(BaseModel):
    place_id: uuid.UUID
    source: str
    visit_date: Optional[date_type] = None


class VisitOut(BaseModel):
    id: uuid.UUID
    place_id: uuid.UUID
    source: Optional[str]
    visit_date: Optional[date_type]
    visited_at: datetime
    rated: bool

    class Config:
        from_attributes = True


@router.post("", response_model=VisitOut, status_code=201)
async def create_visit(
    body: CreateVisitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visit = UserVisit(
        user_id=current_user.id,
        place_id=body.place_id,
        source=body.source,
        visit_date=body.visit_date,
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return visit


@router.get("/pending", response_model=list[VisitOut])
async def get_pending_visits(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns unrated visits whose visit_date is today or in the past."""
    today = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(UserVisit).where(
            UserVisit.user_id == current_user.id,
            UserVisit.rated == False,  # noqa: E712
            UserVisit.visit_date <= today,
        )
    )
    return list(result.scalars().all())


@router.get("/place/{place_id}", response_model=list[VisitOut])
async def get_place_visits(
    place_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserVisit).where(
            UserVisit.user_id == current_user.id,
            UserVisit.place_id == place_id,
        ).order_by(UserVisit.visited_at.desc())
    )
    return list(result.scalars().all())
