import asyncio

from scripts.evaluate_agent_quality import build_report


def test_agent_quality_gates_cover_workflow_and_context_engineering():
    report = asyncio.run(build_report())

    assert report["routing"]["total"] >= 50
    assert report["workflow_detection"]["total"] >= 20
    assert report["context_selection"]["total"] >= 20
    assert report["passed"] is True
