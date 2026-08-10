from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


class PlannerDecision(BaseModel):
    """A compact, auditable planner decision. It intentionally excludes chain of thought."""

    action: Literal["tool", "respond"] = "respond"
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="直接回复用户", max_length=120)


@dataclass
class AgentTraceEvent:
    type: Literal["status", "plan", "tool_call", "tool_result", "guardrail", "error"]
    title: str
    detail: str = ""
    step: int = 0
    tool: str | None = None
    success: bool | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "detail": self.detail,
            "step": self.step,
            "tool": self.tool,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ToolObservation:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    success: bool
    status: str = "completed"

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "status": self.status,
            "success": self.success,
            "result": self.result,
        }


@dataclass
class AgentRunResult:
    run_id: str
    response_messages: list[dict[str, Any]]
    trace: list[AgentTraceEvent] = field(default_factory=list)
    observations: list[ToolObservation] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    pending_action: dict[str, Any] | None = None

    def trace_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.trace]
