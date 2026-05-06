import uuid
from datetime import datetime, date, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Enum as SAEnum
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


class DifficultyEnum(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    difficulty = Column(SAEnum(DifficultyEnum), default=DifficultyEnum.medium)
    scheduled_date = Column(Date, nullable=False, index=True)
    status = Column(SAEnum(TaskStatusEnum), default=TaskStatusEnum.pending)
    completion_proof = Column(Text)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="tasks")
