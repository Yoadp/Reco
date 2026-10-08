import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user, get_current_moderator
from app.models.recommendation import Recommendation, Vote
from app.models.user import User
from app.models.place import Place
from app.services.points import award_points, check_auto_approve, POINTS

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationCreate(BaseModel):
    place_id: uuid.UUID
    content: str
    tags: Optional[List[str]] = None


class RecommendationOut(BaseModel):
    id: uuid.UUID
    place_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    tags: Optional[List[str]]
    status: str
    upvotes: int
    downvotes: int
    points_awarded: Optional[int]

    class Config:
        from_attributes = True


class ModerateRequest(BaseModel):
    action: str  # "approve" | "reject" | "spam"


@router.post("", response_model=RecommendationOut, status_code=status.HTTP_201_CREATED)
async def create_recommendation(
    body: RecommendationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    place = await db.get(Place, body.place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    rec = Recommendation(
        user_id=user.id,
        place_id=body.place_id,
        content=body.content,
        tags=body.tags,
    )
    db.add(rec)
    await db.flush()

    # bonus for first recommendation on a place
    existing = await db.execute(
        select(Recommendation)
        .where(Recommendation.place_id == body.place_id, Recommendation.id != rec.id)
    )
    if existing.first() is None:
        await award_points(db, user.id, POINTS["first_rec_bonus"], "first_rec", rec.id)

    await db.commit()
    await db.refresh(rec)
    return rec


@router.get("/place/{place_id}", response_model=List[RecommendationOut])
async def list_recommendations(
    place_id: uuid.UUID,
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Recommendation).where(Recommendation.place_id == place_id)
    if status_filter:
        stmt = stmt.where(Recommendation.status == status_filter)
    else:
        stmt = stmt.where(Recommendation.status == "approved")
    stmt = stmt.order_by(
        (Recommendation.upvotes - Recommendation.downvotes).desc(),
        Recommendation.created_at.desc(),
    ).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/{rec_id}/vote")
async def vote(
    rec_id: uuid.UUID,
    value: int,  # +1 or -1 as query param
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if value not in (1, -1):
        raise HTTPException(status_code=400, detail="value must be 1 or -1")

    existing = await db.execute(
        select(Vote).where(Vote.recommendation_id == rec_id, Vote.user_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already voted")

    rec = await db.get(Recommendation, rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot vote on your own recommendation")

    vote_obj = Vote(user_id=user.id, recommendation_id=rec_id, value=value)
    db.add(vote_obj)

    if value == 1:
        rec.upvotes += 1
    else:
        rec.downvotes += 1

    await db.flush()
    await check_auto_approve(db, rec_id)
    await db.commit()
    return {"upvotes": rec.upvotes, "downvotes": rec.downvotes, "status": rec.status}


@router.post("/{rec_id}/moderate", dependencies=[Depends(get_current_moderator)])
async def moderate(
    rec_id: uuid.UUID,
    body: ModerateRequest,
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(Recommendation, rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    if body.action == "approve":
        rec.status = "approved"
        delta = POINTS["moderator_approved"]
        reason = "moderator_approved"
    elif body.action == "reject":
        rec.status = "rejected"
        delta = POINTS["inaccurate"]
        reason = "inaccurate"
    elif body.action == "spam":
        rec.status = "rejected"
        delta = POINTS["spam"]
        reason = "spam"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await award_points(db, rec.user_id, delta, reason, rec.id)
    rec.points_awarded = delta
    await db.commit()
    return {"status": rec.status, "points_delta": delta}
