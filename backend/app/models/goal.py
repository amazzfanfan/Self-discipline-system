"""
Goal Model - 用户目标模型
用于存储用户的身体管理目标，支持向量语义检索
"""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class GoalType(str, enum.Enum):
    """目标类型"""
    exercise = "exercise"    # 运动
    diet = "diet"            # 饮食
    sleep = "sleep"          # 睡眠
    appearance = "appearance" # 外貌


class GoalStatus(str, enum.Enum):
    """目标状态"""
    active = "active"        # 进行中
    completed = "completed"  # 已完成
    paused = "paused"        # 已暂停


class GoalSource(str, enum.Enum):
    """目标来源"""
    manual = "manual"        # 手动创建
    chat = "chat"            # 聊天中产生


class Goal(Base):
    """用户目标模型"""
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # 目标内容
    content = Column(Text, nullable=False)  # 原始目标描述
    goal_type = Column(String(50), nullable=False, index=True)  # exercise/diet/sleep/appearance

    # 结构化数据
    structured_data = Column(JSON, nullable=True)  # AI 解析后的结构化数据
    target_metric = Column(String(100))
    target_value = Column(Float)
    current_value = Column(Float)
    progress_mode = Column(String(20), nullable=False, default="sessions")
    completed_sessions = Column(Integer, nullable=False, default=0)
    last_progress_at = Column(DateTime(timezone=True))
    deadline = Column(Date)
    milestones = Column(JSON, nullable=False, default=list)
    recurrence = Column(String(20), nullable=False, default="flexible")
    days_of_week = Column(JSON, nullable=False, default=list)
    preferred_time = Column(Time)
    duration_minutes = Column(Integer)
    start_date = Column(Date)
    reminder_enabled = Column(Boolean, nullable=False, default=False)
    reminder_minutes_before = Column(Integer, nullable=False, default=30)

    # 向量嵌入
    # 向量由远程百炼 Embedding API 生成；本地 pgvector 只负责存储与检索。
    embedding = Column(Vector(1536))
    embedding_model = Column(String(100))

    # 评分和状态
    importance_score = Column(Float, default=0.5)  # 0-1 重要性评分
    status = Column(String(20), default="active", index=True)  # active/completed/paused

    # 来源
    source = Column(String(20), default="manual")  # manual/chat

    # 时间戳
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # 复合索引
    __table_args__ = (
        Index("idx_goals_user_type", "user_id", "goal_type"),
        Index("idx_goals_user_status", "user_id", "status"),
        Index("idx_goals_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Goal {self.id}: {self.content[:50]}...>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "content": self.content,
            "goal_type": self.goal_type,
            "structured_data": self.structured_data,
            "target_metric": self.target_metric,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "progress_mode": self.progress_mode,
            "completed_sessions": self.completed_sessions or 0,
            "last_progress_at": (
                self.last_progress_at.isoformat() if self.last_progress_at else None
            ),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "milestones": self.milestones or [],
            "recurrence": self.recurrence,
            "days_of_week": self.days_of_week or [],
            "preferred_time": (
                self.preferred_time.strftime("%H:%M") if self.preferred_time else None
            ),
            "duration_minutes": self.duration_minutes,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "reminder_enabled": self.reminder_enabled,
            "reminder_minutes_before": self.reminder_minutes_before,
            "embedding_model": self.embedding_model,
            "importance_score": self.importance_score,
            "status": self.status,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class GoalProgressEvent(Base):
    """Immutable evidence that changed a goal's execution progress."""

    __tablename__ = "goal_progress_events"
    __table_args__ = (
        UniqueConstraint(
            "goal_id",
            "task_id",
            "event_type",
            name="uq_goal_progress_task_event",
        ),
        Index("ix_goal_progress_goal_created", "goal_id", "created_at"),
        Index("ix_goal_progress_user_date", "user_id", "event_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
    )
    event_type = Column(String(32), nullable=False)
    delta = Column(Float, nullable=False, default=0)
    previous_value = Column(Float)
    current_value = Column(Float)
    event_date = Column(Date, nullable=False)
    source = Column(String(30), nullable=False, default="system")
    event_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
