import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Time, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class GenderEnum(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(100), nullable=False)
    avatar_url = Column(String(500))
    # Deprecated legacy provider settings kept in metadata for backward-compatible
    # migrations. Runtime model credentials are server-side environment variables.
    llm_api_key = Column(String(500))
    llm_base_url = Column(String(500))
    llm_model = Column(String(200))
    embedding_api_key = Column(String)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    scores = relationship("UserScore", back_populates="user")
    tasks = relationship("Task", back_populates="user")
    assessment_runs = relationship("AssessmentRun", back_populates="user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    height_cm = Column(Numeric(5, 1))
    weight_kg = Column(Numeric(5, 1))
    age = Column(Integer)
    gender = Column(SAEnum(GenderEnum))
    body_fat_pct = Column(Numeric(4, 1))
    avatar_url = Column(String(500))           # 头像（仅显示）
    portrait_photo_url = Column(String(500))   # 正面肖像图（旷视分析）
    front_photo_url = Column(String(500))      # 兼容历史数据；不再采集
    side_photo_url = Column(String(500))       # 兼容历史数据；不再采集
    ai_profile_score = Column(JSON)
    questionnaire = Column(JSON, nullable=True)
    skin_analysis = Column(JSON, nullable=True)  # face++ 肤质分析结果
    skincare_constraints = Column(JSON, nullable=False, default=dict)
    task_constraints = Column(JSON, nullable=False, default=dict)
    daily_task_budget = Column(Integer, nullable=False, default=3)
    memory_enabled = Column(Integer, nullable=False, default=1)
    notification_settings = Column(JSON, nullable=False, default=dict)
    notification_quiet_start = Column(Time)
    notification_quiet_end = Column(Time)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profile")
