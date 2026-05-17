"""
Memory Model - 向量记忆模型
用于存储对话记忆和向量嵌入，支持语义检索
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Memory(Base):
    """向量记忆模型"""
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # 原始内容
    content = Column(Text, nullable=False)
    role = Column(String(20), nullable=False)  # user, system
    
    # 向量嵌入
    embedding = Column(Vector(1536))  # OpenAI ada-002 维度
    
    # 元数据
    memory_type = Column(String(50), default="conversation")  # conversation, preference, fact
    importance_score = Column(Float, default=0.5)  # 0-1 重要性评分
    source_id = Column(String(100))  # 来源 ID（如对话 ID）
    
    # 访问统计
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime(timezone=True))
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 复合索引
    __table_args__ = (
        Index("idx_memories_user_type", "user_id", "memory_type"),
        Index("idx_memories_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Memory {self.id}: {self.content[:50]}...>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "content": self.content,
            "role": self.role,
            "memory_type": self.memory_type,
            "importance_score": self.importance_score,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "created_at": self.created_at.isoformat(),
        }
