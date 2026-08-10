import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Date, ForeignKey, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class WeightRecord(Base):
    __tablename__ = "weight_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    weight_kg = Column(Numeric(5, 1), nullable=False)
    recorded_at = Column(Date, nullable=False)
    ai_evaluation = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
