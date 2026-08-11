import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class AssessmentRun(Base):
    __tablename__ = "assessment_runs"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "input_hash",
            "rubric_version",
            name="uq_assessment_run_user_input_version",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    input_hash = Column(String(64), nullable=False, index=True)
    rubric_version = Column(String(64), nullable=False)
    mode = Column(String(32), nullable=False, default="rules")
    scores = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False)
    confidence = Column(JSON, nullable=False)
    overall_confidence = Column(Numeric(3, 2), nullable=False)
    warnings = Column(JSON, nullable=False, default=list)
    skin_source = Column(String(32), nullable=False, default="none")
    skin_input_hash = Column(String(64))
    reused = Column(Boolean, nullable=False, default=False)
    generation_status = Column(String(24), nullable=False, default="pending")
    generation_stage = Column(String(32), nullable=False, default="queued")
    generation_error = Column(String(120))
    care_suggestions = Column(JSON, nullable=False, default=list)
    profile_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
    )
    generation_started_at = Column(DateTime(timezone=True))
    generation_completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="assessment_runs")
