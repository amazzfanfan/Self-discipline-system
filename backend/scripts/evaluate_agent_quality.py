"""Offline quality gates for routing, workflow activation and context selection.

Run with:
    python -m scripts.evaluate_agent_quality
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from app.agent.runtime import AgentRuntime
from app.services.user_context_service import select_context
from scripts.evaluate_agent import evaluate_cases, load_cases


EVAL_DIR = Path(__file__).parents[1] / "evals"
WORKFLOW_DATASET = EVAL_DIR / "agent_workflow_cases.jsonl"
CONTEXT_DATASET = EVAL_DIR / "context_selection_cases.jsonl"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate_workflow_detection(cases: list[dict]) -> dict:
    results = []
    false_positives = 0
    for case in cases:
        actual = AgentRuntime._requires_multi_tool_workflow(case["input"])
        passed = actual is bool(case["expected"])
        if actual and not case["expected"]:
            false_positives += 1
        results.append({**case, "actual": actual, "passed": passed})
    total = len(results)
    negatives = sum(not item["expected"] for item in cases)
    return {
        "total": total,
        "accuracy": round(sum(item["passed"] for item in results) / total, 4) if total else 0,
        "false_positive_rate": round(false_positives / negatives, 4) if negatives else 0,
        "failures": [item for item in results if not item["passed"]],
    }


def evaluate_context_selection(cases: list[dict]) -> dict:
    results = []
    for case in cases:
        selection = select_context(case["input"])
        actual_sections = selection.labels()
        actual_dimensions = list(selection.dimensions)
        passed = (
            actual_sections == case["expected_sections"]
            and actual_dimensions == case["expected_dimensions"]
        )
        results.append(
            {
                **case,
                "actual_sections": actual_sections,
                "actual_dimensions": actual_dimensions,
                "passed": passed,
            }
        )
    total = len(results)
    return {
        "total": total,
        "exact_match_accuracy": round(
            sum(item["passed"] for item in results) / total,
            4,
        ) if total else 0,
        "failures": [item for item in results if not item["passed"]],
    }


async def build_report() -> dict:
    routing = await evaluate_cases(load_cases())
    workflow = evaluate_workflow_detection(_load_jsonl(WORKFLOW_DATASET))
    context = evaluate_context_selection(_load_jsonl(CONTEXT_DATASET))
    gates = {
        "routing_tool_accuracy": routing.tool_accuracy >= 0.98,
        "unsafe_write_rate": routing.unsafe_write_rate == 0,
        "workflow_detection_accuracy": workflow["accuracy"] >= 0.95,
        "workflow_false_positive_rate": workflow["false_positive_rate"] <= 0.05,
        "context_exact_match_accuracy": context["exact_match_accuracy"] >= 0.95,
    }
    return {
        "routing": asdict(routing),
        "workflow_detection": workflow,
        "context_selection": context,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    report = asyncio.run(build_report())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
