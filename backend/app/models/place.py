import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, Float, Integer, DateTime, JSON, ForeignKey, Text, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(String(500))
    city: Mapped[str] = mapped_column(String(100), index=True)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    cuisine: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    price_range: Mapped[Optional[int]] = mapped_column(Integer)  # 1-4
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    hours: Mapped[Optional[dict]] = mapped_column(JSON)
    photos: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    aggregated_score: Mapped[Optional[float]] = mapped_column(Float)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sources: Mapped[List["DataSource"]] = relationship("DataSource", back_populates="place", cascade="all, delete-orphan")
    recommendations: Mapped[List["Recommendation"]] = relationship("Recommendation", back_populates="place")


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(50))  # google_places, yelp, article, menu, tabit, ontopo
    source_name: Mapped[Optional[str]] = mapped_column(String(100))  # human label: "Google", "rest.co.il"
    url: Mapped[Optional[str]] = mapped_column(String(1000))
    excerpt: Mapped[Optional[str]] = mapped_column(Text)  # short quote or snippet from the source
    review_count: Mapped[Optional[int]] = mapped_column(Integer)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    place: Mapped["Place"] = relationship("Place", back_populates="sources")
