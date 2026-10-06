import uuid
from datetime import datetime, timezone, date as date_type

from sqlalchemy import String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class UserVisit(Base):
    __tablename__ = "user_visits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    place_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=True)   # tabit | ontopo | wolt | walk-in
    visit_date: Mapped[date_type] = mapped_column(Date, nullable=True)
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    rated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
