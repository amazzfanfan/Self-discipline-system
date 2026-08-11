"""Chat API backed by the guarded Agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import AgentRuntime
from app.agent.tools import ToolRegistry
from app.agent.types import AgentRunResult, AgentTraceEvent
from app.core.database import async_session, get_db
from app.core.deps import get_current_user
from app.models.agent_run import PendingAction
from app.models.conversation import Conversation, RoleEnum
from app.models.user import User
from app.services.llm_service import (
    begin_llm_metrics,
    chat_completion_stream_with_fallback,
    chat_completion_with_fallback,
    get_llm_metrics,
)
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.agent_audit_service import get_pending_action, update_agent_run_metrics
from app.services.cache_service import enqueue_background_job


router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)
background_tasks: set[asyncio.Task] = set()


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


async def _find_contextual_confirmation(
    db: AsyncSession,
    user_id,
    content: str,
) -> PendingAction | None:
    """Resolve a short follow-up such as “跳过” against the latest pending action."""
    text = content.strip()
    if not re.fullmatch(r"(?:确认|确认执行|执行|确定|是|是的|跳过|删除|继续)", text):
        return None
    result = await db.execute(
        select(PendingAction)
        .where(
            PendingAction.user_id == user_id,
            PendingAction.status == "pending",
            PendingAction.expires_at > datetime.now(timezone.utc),
        )
        .order_by(PendingAction.created_at.desc())
        .limit(1)
    )
    action = result.scalar_one_or_none()
    if not action:
        return None
    if action.tool_name == "skip_task" and text in {"跳过", "继续", "确认", "确认执行", "执行", "确定", "是", "是的"}:
        return action
    if action.tool_name == "delete_goal" and text in {"删除", "继续", "确认", "确认执行", "执行", "确定", "是", "是的"}:
        return action
    return None


def _confirmed_request(action: PendingAction, content: str) -> str:
    suffix = "确认跳过任务" if action.tool_name == "skip_task" else "确认删除目标"
    return f"{action.original_request}\n用户随后回复“{content.strip()}”，已明确{suffix}"


async def _resolve_contextual_confirmation(
    db: AsyncSession,
    action: PendingAction | None,
    run: AgentRunResult,
) -> None:
    if not action:
        return
    observation = next(
        (item for item in run.observations if item.tool == action.tool_name),
        None,
    )
    if not observation:
        return
    action.status = "approved" if observation.success else "failed"
    action.resolved_at = datetime.now(timezone.utc)
    await db.commit()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _fallback_reply(run: AgentRunResult) -> str:
    for observation in run.observations:
        if observation.status == "approval_required":
            return observation.result.get("message", "该操作需要你的明确确认。")
    successful = [item for item in run.observations if item.success]
    if successful:
        return "操作已经完成。你可以在运行轨迹中查看具体结果。"
    return "当前 AI 回复服务暂时不可用，请稍后再试。"


def _direct_operation_reply(run: AgentRunResult) -> str | None:
    """Return fast, factual receipts for writes; advice generation still uses the LLM."""
    if len(run.observations) != 1:
        return None
    observation = run.observations[0]
    if observation.status == "approval_required":
        return str(observation.result.get("message") or "该操作需要你的明确确认。")
    if observation.status == "clarification_required":
        return str(observation.result.get("message") or "请补充执行该操作所需的信息。")
    if not observation.success:
        return None
    result = observation.result
    if observation.tool == "list_today_tasks":
        tasks = result.get("tasks") or []
        dimension_labels = {
            "exercise": "🏃 运动",
            "diet": "🥗 饮食",
            "sleep": "🌙 睡眠",
            "appearance": "✨ 形象管理",
        }
        status_labels = {
            "pending": "待完成",
            "in_progress": "进行中",
            "completed": "已完成",
            "failed": "已跳过",
            "deferred": "已调整",
        }
        def task_status_label(task: dict) -> str:
            disposition_labels = {
                "snoozed": "稍后再做",
                "excused": "今日免做",
                "rescheduled": "已改期",
                "skipped": "已跳过",
                "expired": "已过期",
            }
            return disposition_labels.get(
                task.get("disposition"),
                status_labels.get(task.get("status"), task.get("status", "未知状态")),
            )
        lines = [
            f"- **{dimension_labels.get(task.get('dimension'), task.get('dimension', '任务'))}** · "
            f"{task_status_label(task)}\n  {task.get('title', '')}"
            for task in tasks
        ]
        actionable = sum(task.get("status") in {"pending", "in_progress"} for task in tasks)
        completed = sum(task.get("status") == "completed" for task in tasks)
        snoozed = sum(task.get("disposition") == "snoozed" for task in tasks)
        excused = sum(task.get("disposition") == "excused" for task in tasks)
        skipped = sum(task.get("disposition") in {"skipped", "expired"} for task in tasks)
        summary = f"待完成 {actionable} · 已完成 {completed} · 稍后再做 {snoozed} · 今日免做 {excused} · 未完成 {skipped}"
        return "**今日任务**\n\n" + "\n\n".join(lines) + f"\n\n{summary}。"
    if observation.tool == "create_goal":
        goal = result.get("goal") or {}
        return f"目标已创建并写入系统：**{goal.get('content', '')}**。你可以在“成长目标”页面查看、暂停或编辑。"
    if observation.tool == "update_goal":
        goal = result.get("goal") or {}
        return f"目标已更新：**{result.get('old_content', '')}** → **{goal.get('content', '')}**。"
    if observation.tool == "change_goal_status":
        labels = {"active": "进行中", "paused": "已暂停", "completed": "已完成"}
        return f"目标 **{result.get('content', '')}** 已切换为“{labels.get(result.get('new_status'), result.get('new_status'))}”。"
    if observation.tool == "delete_goal":
        return f"目标 **{result.get('content', '')}** 已永久删除。"
    if observation.tool == "replace_today_task":
        return f"今日任务已真实更新：\n\n- 原任务：{result.get('old_title', '')}\n- 新任务：**{result.get('new_title', '')}**\n\n任务页面已经同步。"
    if observation.tool in {"complete_task", "skip_task", "defer_today_task", "resume_today_task"}:
        return str(result.get("message") or "任务状态已更新。")
    if observation.tool == "record_weight":
        return f"体重已记录：**{result.get('weight_kg', '')} kg**。"
    return None


def _approved_action_reply(tool_name: str, result: dict) -> str:
    if tool_name == "skip_task":
        return str(result.get("message") or "任务已跳过。")
    if tool_name == "delete_goal":
        return f"目标 **{result.get('content', '')}** 已永久删除。"
    if tool_name == "replace_today_task":
        return f"今日任务已更新为：**{result.get('new_title', '')}**。任务页面已经同步。"
    return str(result.get("message") or "操作已经执行完成。")


async def _save_assistant(
    user_id: str,
    user_message_id: str,
    reply: str,
    run: AgentRunResult,
) -> None:
    """Persist the reply and audit metadata in a fresh transaction."""
    async with async_session() as session:
        owner_id = uuid.UUID(user_id)
        source_message_id = uuid.UUID(user_message_id)
        user_message = await session.get(Conversation, source_message_id)
        if user_message:
            user_message.extra_metadata = {
                "agent_status": "completed",
                "run_id": run.run_id,
            }
        assistant = Conversation(
            user_id=owner_id,
            role=RoleEnum.system,
            content=reply,
            extra_metadata={
                "agent_run": {
                    "run_id": run.run_id,
                    "trace": run.trace_dicts(),
                    "metrics": run.metrics,
                    "pending_action": run.pending_action,
                }
            },
        )
        session.add(assistant)
        await session.commit()


async def _learn_from_user(user_id: str, user_message_id: str, content: str) -> None:
    """Run non-critical memory extraction after the response is complete."""
    async with async_session() as session:
        try:
            await MemoryService(session).auto_store_conversation(
                user_id=user_id,
                content=content,
                role="user",
                source_id=user_message_id,
            )
        except Exception as exc:
            logger.warning(f"Agent post-processing failed: {exc}")


async def _launch_learning(user_id: str, user_message_id: str, content: str) -> None:
    queued = await enqueue_background_job(
        "learn_from_user",
        {"user_id": user_id, "user_message_id": user_message_id, "content": content},
    )
    if queued:
        return
    # Development fallback when Redis is temporarily unavailable.
    task = asyncio.create_task(_learn_from_user(user_id, user_message_id, content))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


@router.post("/send")
async def send_message(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Execute an Agent run and return a non-streaming response with its trace."""
    content = body.content.strip()
    contextual_action = await _find_contextual_confirmation(db, user.id, content)
    runtime_content = _confirmed_request(contextual_action, content) if contextual_action else content
    begin_llm_metrics()
    user_message = Conversation(
        user_id=user.id,
        role=RoleEnum.user,
        content=content,
        extra_metadata={"agent_status": "running"},
    )
    db.add(user_message)
    await db.commit()

    run = await AgentRuntime(db, user).run(
        runtime_content,
        user_message_id=user_message.id,
        confirmed_action={
            "tool": contextual_action.tool_name,
            "arguments": contextual_action.arguments,
        }
        if contextual_action
        else None,
    )
    await _resolve_contextual_confirmation(db, contextual_action, run)
    response_started = time.perf_counter()
    reply = _direct_operation_reply(run)
    if reply is None:
        try:
            reply = await chat_completion_with_fallback(
                run.response_messages,
                enable_thinking=False,
                num_retries=0,
                timeout=30,
            )
        except Exception as exc:
            logger.error(f"Agent response generation failed: {exc}")
            reply = _fallback_reply(run)
    run.metrics["response_duration_ms"] = int(
        (time.perf_counter() - response_started) * 1000
    )
    run.metrics.update(get_llm_metrics())
    await update_agent_run_metrics(run.run_id, run.metrics)

    await _save_assistant(str(user.id), str(user_message.id), reply, run)
    await _launch_learning(str(user.id), str(user_message.id), content)
    return {
        "reply": reply,
        "run_id": run.run_id,
        "trace": run.trace_dicts(),
        "metrics": run.metrics,
        "pending_action": run.pending_action,
    }


@router.post("/stream")
async def stream_message(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Stream Agent trace events first, then the final natural-language response."""
    content = body.content.strip()
    contextual_action = await _find_contextual_confirmation(db, user.id, content)
    runtime_content = _confirmed_request(contextual_action, content) if contextual_action else content
    user_id = str(user.id)
    user_message = Conversation(
        user_id=user.id,
        role=RoleEnum.user,
        content=content,
        extra_metadata={"agent_status": "running"},
    )
    db.add(user_message)
    await db.commit()
    user_message_id = str(user_message.id)

    async def event_generator():
        begin_llm_metrics()
        queue: asyncio.Queue[AgentTraceEvent] = asyncio.Queue()

        async def publish(event: AgentTraceEvent) -> None:
            await queue.put(event)

        runtime = AgentRuntime(db, user)
        run_task = asyncio.create_task(
            runtime.run(
                runtime_content,
                on_event=publish,
                user_message_id=user_message.id,
                confirmed_action={
                    "tool": contextual_action.tool_name,
                    "arguments": contextual_action.arguments,
                }
                if contextual_action
                else None,
            )
        )
        try:
            while not run_task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield _sse({"type": "trace", "trace": event.to_dict()})
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
            raise

        try:
            run = await run_task
        except Exception:
            logger.exception("Agent runtime failed")
            yield _sse({
                "type": "error",
                "message": "Agent 运行失败，请稍后重试。",
                "error_code": "agent_runtime_failed",
            })
            yield "data: [DONE]\n\n"
            return

        await _resolve_contextual_confirmation(db, contextual_action, run)

        yield _sse({
            "type": "run",
            "run_id": run.run_id,
            "metrics": run.metrics,
            "pending_action": run.pending_action,
        })
        response_started = time.perf_counter()
        full_reply: list[str] = []
        direct_reply = _direct_operation_reply(run)
        if direct_reply is not None:
            full_reply.append(direct_reply)
            yield _sse({"type": "content", "content": direct_reply})
        else:
            try:
                async for chunk in chat_completion_stream_with_fallback(
                    run.response_messages,
                    enable_thinking=False,
                    num_retries=0,
                    timeout=30,
                ):
                    full_reply.append(chunk)
                    yield _sse({"type": "content", "content": chunk})
            except Exception as exc:
                logger.error(f"Agent stream generation failed: {exc}")
                if not full_reply:
                    fallback = _fallback_reply(run)
                    full_reply.append(fallback)
                    yield _sse({"type": "content", "content": fallback})

        reply = "".join(full_reply).strip() or _fallback_reply(run)
        run.metrics["response_duration_ms"] = int(
            (time.perf_counter() - response_started) * 1000
        )
        run.metrics.update(get_llm_metrics())
        await update_agent_run_metrics(run.run_id, run.metrics)
        yield _sse({"type": "metrics", "metrics": run.metrics})

        try:
            await _save_assistant(user_id, user_message_id, reply, run)
            await _launch_learning(user_id, user_message_id, content)
        except Exception as exc:
            logger.warning(f"Failed to persist Agent reply: {exc}")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/actions/{action_id}/approve")
async def approve_pending_action(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    action = await get_pending_action(db, action_id, user.id, for_update=True)
    if not action:
        raise HTTPException(404, "待确认操作不存在")
    now = datetime.now(timezone.utc)
    if action.status != "pending" or action.expires_at <= now:
        if action.status == "pending":
            action.status = "expired"
        raise HTTPException(409, "待确认操作已处理或过期")

    action.status = "executing"
    await db.flush()
    confirmation = f"{action.original_request}\n用户已明确确认执行该操作"
    if action.tool_name == "skip_task":
        confirmation += "，确认跳过任务"
    elif action.tool_name == "delete_goal":
        confirmation += "，确认删除目标"
    result, success, status, duration_ms = await ToolRegistry(db, str(user.id)).execute(
        action.tool_name,
        action.arguments,
        confirmation,
    )
    action.status = "approved" if success else "failed"
    action.resolved_at = now
    reply = _approved_action_reply(action.tool_name, result) if success else None
    if reply:
        db.add(
            Conversation(
                user_id=user.id,
                role=RoleEnum.system,
                content=reply,
                extra_metadata={
                    "message_type": "action_result",
                    "action_id": action.action_id,
                    "tool": action.tool_name,
                    "success": True,
                },
            )
        )
    await db.flush()
    return {
        "success": success,
        "status": status,
        "action_status": action.status,
        "result": result,
        "reply": reply,
        "duration_ms": duration_ms,
    }


@router.post("/actions/{action_id}/reject")
async def reject_pending_action(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    action = await get_pending_action(db, action_id, user.id)
    if not action:
        raise HTTPException(404, "待确认操作不存在")
    if action.status != "pending":
        raise HTTPException(409, "待确认操作已处理")
    action.status = "rejected"
    action.resolved_at = datetime.now(timezone.utc)
    return {"message": "操作已取消"}


@router.get("/actions/{action_id}")
async def get_action_status(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    action = await get_pending_action(db, action_id, user.id)
    if not action:
        raise HTTPException(404, "待确认操作不存在")
    status = action.status
    if status == "pending" and action.expires_at <= datetime.now(timezone.utc):
        action.status = "expired"
        action.resolved_at = datetime.now(timezone.utc)
        status = "expired"
    return {
        "action_id": action.action_id,
        "status": status,
        "tool": action.tool_name,
        "arguments": action.arguments,
        "expires_at": action.expires_at.isoformat(),
    }


@router.get("/history")
async def get_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
    limit: int = 50,
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    messages = list(reversed(result.scalars().all()))
    action_ids = {
        pending.get("action_id")
        for message in messages
        if isinstance(message.extra_metadata, dict)
        if isinstance(message.extra_metadata.get("agent_run"), dict)
        if isinstance((pending := message.extra_metadata["agent_run"].get("pending_action")), dict)
        if pending.get("action_id")
    }
    action_statuses: dict[str, str] = {}
    if action_ids:
        action_result = await db.execute(
            select(PendingAction).where(
                PendingAction.user_id == user.id,
                PendingAction.action_id.in_(action_ids),
            )
        )
        now = datetime.now(timezone.utc)
        for action in action_result.scalars().all():
            if action.status == "pending" and action.expires_at <= now:
                action.status = "expired"
                action.resolved_at = now
            action_statuses[action.action_id] = action.status

    payload = [
        {
            "id": str(message.id),
            "role": message.role.value,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "metadata": dict(message.extra_metadata or {}),
        }
        for message in messages
    ]
    for item in payload:
        agent_run = item["metadata"].get("agent_run")
        if not isinstance(agent_run, dict):
            continue
        pending = agent_run.get("pending_action")
        if not isinstance(pending, dict) or pending.get("action_id") not in action_statuses:
            continue
        item["metadata"]["agent_run"] = {
            **agent_run,
            "pending_action": {
                **pending,
                "status": action_statuses[pending["action_id"]],
            },
        }
    return payload


@router.get("/memories")
async def get_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
    limit: int = 20,
    memory_type: str = None,
):
    return await MemoryService(db).get_recent_memories(
        user_id=str(user.id), limit=min(max(limit, 1), 100), memory_type=memory_type
    )


@router.get("/memories/search")
async def search_memories(
    query: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
    top_k: int = 5,
):
    return await MemoryService(db).search_similar_memories(
        user_id=str(user.id), query=query, top_k=min(max(top_k, 1), 20)
    )


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    deleted = await MemoryService(db).delete_memory(memory_id, str(user.id))
    return {"deleted": deleted, "id": memory_id}


@router.get("/memories/stats")
async def get_memory_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await MemoryService(db).get_memory_stats(str(user.id))


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return {"summary": await ProfileService(db).get_user_summary(str(user.id))}
