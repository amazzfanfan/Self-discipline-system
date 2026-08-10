import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agent.types import AgentTraceEvent
from app.core.database import async_session
from app.models.agent_run import AgentRun, AgentStep, PendingAction


async def start_agent_run(run_id: str, user_id, user_message_id=None):
    async with async_session() as session:
        item = AgentRun(
            run_id=run_id,
            user_id=user_id,
            user_message_id=user_message_id,
            status="running",
        )
        session.add(item)
        await session.commit()
        return item.id


async def append_agent_event(agent_run_id, sequence: int, event: AgentTraceEvent) -> None:
    async with async_session() as session:
        session.add(
            AgentStep(
                agent_run_id=agent_run_id,
                sequence=sequence,
                step=event.step,
                event_type=event.type,
                title=event.title[:200],
                detail=(event.detail or "")[:1200],
                tool_name=event.tool,
                success=None if event.success is None else str(event.success).lower(),
                duration_ms=event.duration_ms,
            )
        )
        await session.commit()


async def finish_agent_run(agent_run_id, metrics: dict, status: str = "completed", error_code: str | None = None) -> None:
    async with async_session() as session:
        item = await session.get(AgentRun, agent_run_id)
        if not item:
            return
        item.status = status
        item.metrics = metrics
        item.planner_calls = int(metrics.get("planner_calls", 0))
        item.tool_calls = int(metrics.get("tool_calls", 0))
        item.input_tokens = int(metrics.get("input_tokens", 0))
        item.output_tokens = int(metrics.get("output_tokens", 0))
        item.estimated_cost = float(metrics.get("estimated_cost", 0.0))
        item.error_code = error_code
        item.completed_at = datetime.now(timezone.utc)
        await session.commit()


async def update_agent_run_metrics(run_id: str, metrics: dict) -> None:
    async with async_session() as session:
        result = await session.execute(select(AgentRun).where(AgentRun.run_id == run_id))
        item = result.scalar_one_or_none()
        if not item:
            return
        item.metrics = metrics
        item.planner_calls = int(metrics.get("planner_calls", 0))
        item.tool_calls = int(metrics.get("tool_calls", 0))
        item.input_tokens = int(metrics.get("input_tokens", 0))
        item.output_tokens = int(metrics.get("output_tokens", 0))
        item.estimated_cost = float(metrics.get("estimated_cost", 0.0))
        item.status = str(metrics.get("status", "completed"))
        item.completed_at = datetime.now(timezone.utc)
        await session.commit()


async def create_pending_action(agent_run_id, user_id, tool_name: str, arguments: dict, original_request: str) -> dict:
    async with async_session() as session:
        action_id = uuid.uuid4().hex
        item = PendingAction(
            action_id=action_id,
            user_id=user_id,
            agent_run_id=agent_run_id,
            tool_name=tool_name,
            arguments=arguments,
            original_request=original_request,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.add(item)
        await session.commit()
        return {
            "action_id": action_id,
            "tool": tool_name,
            "arguments": arguments,
            "expires_at": item.expires_at.isoformat(),
            "status": "pending",
        }


async def get_pending_action(session, action_id: str, user_id, *, for_update: bool = False):
    query = select(PendingAction).where(
        PendingAction.action_id == action_id,
        PendingAction.user_id == user_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()
