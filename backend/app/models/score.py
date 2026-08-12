import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Numeric, Integer, Enum as SAEnum, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class DimensionEnum(str, enum.Enum):
    exercise = "exercise"
    diet = "diet"
    sleep = "sleep"
    appearance = "appearance"


class UserScore(Base):
    __tablename__ = "user_scores"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "dimension",
            name="uq_user_scores_user_dimension",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    score = Column(Numeric(4, 1), default=50.0)
    baseline_score = Column(Numeric(4, 1), default=50.0, nullable=False)
    total_positive_count = Column(Integer, default=0)
    total_negative_count = Column(Integer, default=0)
    streak_days = Column(Integer, default=0)
    last_completed_date = Column(Date)
    last_score_change = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="scores")


class ScoreHistory(Base):
    __tablename__ = "score_history"
    __table_args__ = (
        Index(
            "ix_score_history_user_dimension_created",
            "user_id",
            "dimension",
            "created_at",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    delta = Column(Numeric(3, 1), nullable=False)
    reason = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
