import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.runtime import AgentRuntime
from scripts.evaluate_agent import OFFLINE_EVAL_NOW


CASES = [
    json.loads(line)
    for line in (Path(__file__).parents[1] / "evals" / "agent_safety_cases.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case['category']}:{case['input'][:12]}")
def test_deterministic_fallback_agent_safety_dataset(case, monkeypatch):
    db = MagicMock()
    db.rollback = AsyncMock()
    runtime = AgentRuntime(db, SimpleNamespace(id="00000000-0000-0000-0000-000000000001", nickname="Eval"))
    monkeypatch.setattr("app.agent.runtime.local_now", lambda: OFFLINE_EVAL_NOW)

    decision = runtime._fallback_decision(case["input"], [])

    assert decision.tool == case["expected_tool"]
    if "expected_arguments" in case:
        assert decision.arguments == case["expected_arguments"]
