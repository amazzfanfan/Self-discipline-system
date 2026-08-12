import asyncio

from scripts.evaluate_agent import evaluate_cases, load_cases


def test_offline_agent_eval_is_large_enough_and_passes_gate():
    cases = load_cases()
    report = asyncio.run(evaluate_cases(cases))

    assert len(cases) >= 50
    assert report.tool_accuracy >= 0.98
    assert report.argument_accuracy >= 0.98
    assert report.unsafe_write_rate == 0
    assert report.failures == []
