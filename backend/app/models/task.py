import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Integer, JSON, Enum as SAEnum, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum
from app.models.score import DimensionEnum


class TaskStatusEnum(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    deferred = "deferred"


class DifficultyEnum(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "dimension",
            "scheduled_date",
            name="uq_tasks_user_dimension_date",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    difficulty = Column(SAEnum(DifficultyEnum), default=DifficultyEnum.medium)
    scheduled_date = Column(Date, nullable=False, index=True)
    status = Column(SAEnum(TaskStatusEnum), default=TaskStatusEnum.pending)
    completion_proof = Column(Text)
    rationale = Column(Text)
    estimated_minutes = Column(String(20))
    user_feedback = Column(String(30))
    source = Column(String(30), default="adaptive")
    disposition = Column(String(20))
    disposition_reason = Column(String(200))
    deferred_until = Column(DateTime(timezone=True))
    defer_count = Column(Integer, nullable=False, default=0)
    original_scheduled_date = Column(Date)
    adaptation_metadata = Column(JSON, nullable=False, default=dict)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="tasks")
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        Index("ix_task_events_task_created", "task_id", "created_at"),
        Index("ix_task_events_user_created", "user_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    from_status = Column(String(24))
    to_status = Column(String(24))
    reason = Column(String(200))
    actor = Column(String(20), nullable=False, default="system")
    source = Column(String(30), nullable=False, default="system")
    event_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    task = relationship("Task", back_populates="events")
