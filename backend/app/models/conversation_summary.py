import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ConversationSummary(Base):
    """Rolling episodic summary for messages outside the verbatim context window."""

    __tablename__ = "conversation_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_conversation_summaries_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary = Column(JSON, nullable=False, default=dict)
    through_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
    )
    through_created_at = Column(DateTime(timezone=True))
    summarized_message_count = Column(Integer, nullable=False, default=0)
    version = Column(String(40), nullable=False, default="conversation-summary-v1")
    cleared_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
