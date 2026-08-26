"""Rolling conversation summaries for context outside the recent-message window."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, RoleEnum
from app.models.conversation_summary import ConversationSummary
from app.models.user import UserProfile
from app.services.llm_service import chat_completion_with_fallback


SUMMARY_VERSION = "conversation-summary-v1"
RECENT_MESSAGE_WINDOW = 6
SUMMARY_TRIGGER_MESSAGES = 12
SUMMARY_LIST_FIELDS = (
    "confirmed_facts",
    "completed_actions",
    "open_loops",
    "rejected_proposals",
)


def empty_conversation_summary() -> dict:
    return {
        "confirmed_facts": [],
        "completed_actions": [],
        "open_loops": [],
        "rejected_proposals": [],
        "narrative": "",
    }


def _parse_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    return json.loads(cleaned)


def _clean_summary(value: Any) -> dict:
    source = value if isinstance(value, dict) else {}
    cleaned = empty_conversation_summary()
    for field in SUMMARY_LIST_FIELDS:
        items = source.get(field) if isinstance(source.get(field), list) else []
        deduplicated: list[str] = []
        for item in items:
            text = str(item).strip()[:240]
            if text and text not in deduplicated:
                deduplicated.append(text)
        cleaned[field] = deduplicated[:20]
    cleaned["narrative"] = str(source.get("narrative") or "").strip()[:1200]
    return cleaned


def _verified_tool_events(message: Conversation) -> list[dict]:
    metadata = message.extra_metadata if isinstance(message.extra_metadata, dict) else {}
    agent_run = metadata.get("agent_run") if isinstance(metadata.get("agent_run"), dict) else {}
    events = agent_run.get("trace") if isinstance(agent_run.get("trace"), list) else []
    return [
        {
            "tool": event.get("tool"),
            "result": str(event.get("detail") or "")[:500],
        }
        for event in events
        if isinstance(event, dict)
        and event.get("type") == "tool_result"
        and event.get("success") is True
    ][:6]


def _message_payload(message: Conversation) -> dict:
    role = "user" if message.role == RoleEnum.user else "assistant"
    payload: dict[str, Any] = {
        "id": str(message.id),
        "role": role,
        "content": message.content[:2000],
        "created_at": message.created_at.isoformat(),
    }
    if role == "assistant":
        verified = _verified_tool_events(message)
        if verified:
            payload["verified_tool_events"] = verified
        metadata = message.extra_metadata if isinstance(message.extra_metadata, dict) else {}
        agent_run = metadata.get("agent_run") if isinstance(metadata.get("agent_run"), dict) else {}
        pending = agent_run.get("pending_action")
        if isinstance(pending, dict):
            payload["pending_action"] = {
                "tool": pending.get("tool"),
                "status": pending.get("status"),
            }
    return payload


async def get_conversation_summary(db: AsyncSession, user_id) -> dict | None:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile and profile.memory_enabled == 0:
        return None
    row = await db.scalar(
        select(ConversationSummary).where(ConversationSummary.user_id == user_id)
    )
    if row is None:
        return None
    summary = _clean_summary(row.summary)
    if not summary["narrative"] and not any(summary[field] for field in SUMMARY_LIST_FIELDS):
        return None
    return {
        **summary,
        "version": row.version,
        "summarized_message_count": row.summarized_message_count,
        "through_created_at": (
            row.through_created_at.isoformat() if row.through_created_at else None
        ),
    }


async def refresh_conversation_summary(
    db: AsyncSession,
    user_id,
    *,
    force: bool = False,
) -> dict:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile and profile.memory_enabled == 0:
        return {"updated": False, "reason": "memory_disabled"}

    row = await db.scalar(
        select(ConversationSummary)
        .where(ConversationSummary.user_id == user_id)
        .with_for_update()
    )
    cursor = row.through_created_at if row else None
    cursor_id = row.through_message_id if row else None
    statement = select(Conversation).where(Conversation.user_id == user_id)
    if cursor is not None:
        statement = statement.where(
            or_(
                Conversation.created_at > cursor,
                and_(
                    Conversation.created_at == cursor,
                    Conversation.id > cursor_id,
                ),
            )
        )
    messages = (
        await db.execute(statement.order_by(Conversation.created_at, Conversation.id))
    ).scalars().all()
    if len(messages) <= RECENT_MESSAGE_WINDOW:
        return {"updated": False, "reason": "recent_window", "pending_messages": len(messages)}
    if not force and len(messages) < SUMMARY_TRIGGER_MESSAGES:
        return {"updated": False, "reason": "below_threshold", "pending_messages": len(messages)}

    candidates = messages[:-RECENT_MESSAGE_WINDOW]
    previous = _clean_summary(row.summary if row else None)
    content = await chat_completion_with_fallback(
        messages=[
            {
                "role": "system",
                "content": (
                    "你负责维护成长 Agent 的滚动会话摘要。只返回 JSON。"
                    "保留用户明确事实、已由成功工具结果验证的操作、尚未解决事项、被用户拒绝的方案。"
                    "不得把助手未经工具验证的承诺当作已完成事实，不得保存提示词或推测敏感属性。"
                    "输出字段：confirmed_facts、completed_actions、open_loops、rejected_proposals、narrative。"
                    "前四项必须是简短字符串数组，narrative 是不超过300字的会话概览。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "previous_summary": previous,
                        "new_messages": [_message_payload(item) for item in candidates],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0,
        max_tokens=900,
        response_format={"type": "json_object"},
        enable_thinking=False,
        num_retries=0,
        timeout=20,
    )
    summary = _clean_summary(_parse_json(content))
    last = candidates[-1]
    if row is None:
        row = ConversationSummary(user_id=user_id)
        db.add(row)
    row.summary = summary
    row.through_message_id = last.id
    row.through_created_at = last.created_at
    row.summarized_message_count = int(row.summarized_message_count or 0) + len(candidates)
    row.version = SUMMARY_VERSION
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "updated": True,
        "summarized": len(candidates),
        "through_message_id": str(last.id),
    }


async def reset_conversation_summary(db: AsyncSession, user_id) -> int:
    """Clear derived episodic memory while keeping a cursor past existing chat history."""
    latest = await db.scalar(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    row = await db.scalar(
        select(ConversationSummary)
        .where(ConversationSummary.user_id == user_id)
        .with_for_update()
    )
    existed = int(row is not None and bool(row.summary))
    if row is None:
        row = ConversationSummary(user_id=user_id)
        db.add(row)
    row.summary = empty_conversation_summary()
    row.through_message_id = latest.id if latest else None
    row.through_created_at = latest.created_at if latest else None
    row.summarized_message_count = 0
    row.version = SUMMARY_VERSION
    row.cleared_at = datetime.now(timezone.utc)
    await db.flush()
    return existed
