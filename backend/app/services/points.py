from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.recommendation import Recommendation, PointsTransaction

POINTS = {
    "community_approved": 10,
    "moderator_approved": 5,
    "first_rec_bonus": 3,
    "inaccurate": -8,
    "spam": -15,
    "saved_by_10": 5,
}

TIER_THRESHOLDS = {"silver": 100, "gold": 500}


def compute_tier(points: int) -> str:
    if points >= TIER_THRESHOLDS["gold"]:
        return "gold"
    if points >= TIER_THRESHOLDS["silver"]:
        return "silver"
    return "bronze"


async def award_points(
    db: AsyncSession,
    user_id,
    delta: int,
    reason: str,
    recommendation_id=None,
) -> PointsTransaction:
    tx = PointsTransaction(
        user_id=user_id,
        recommendation_id=recommendation_id,
        delta=delta,
        reason=reason,
    )
    db.add(tx)

    user = await db.get(User, user_id)
    user.points_balance = max(0, user.points_balance + delta)
    user.tier = compute_tier(user.points_balance)

    await db.flush()
    return tx


async def check_auto_approve(db: AsyncSession, recommendation_id) -> bool:
    """Return True if recommendation crosses the community auto-approve threshold."""
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None or rec.status != "pending":
        return False
    total = rec.upvotes + rec.downvotes
    if total >= 10 and rec.upvotes / total >= 0.70:
        rec.status = "approved"
        await award_points(db, rec.user_id, POINTS["community_approved"], "community_approved", rec.id)
        return True
    if rec.downvotes >= 5:
        rec.status = "flagged"
    return False
