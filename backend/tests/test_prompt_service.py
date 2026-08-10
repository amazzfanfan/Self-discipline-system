from app.services.prompt_service import PromptService


def test_build_skin_suggestion_prompt_keeps_json_example() -> None:
    prompt = PromptService().build_skin_suggestion_prompt(
        skin_type_name="油性皮肤",
        issues_str="痘痘、黑头",
    )

    assert "油性皮肤" in prompt
    assert "痘痘、黑头" in prompt
    assert '{"suggestions": ["建议1", "建议2", "建议3"]}' in prompt


def test_build_skin_task_prompt_keeps_json_example() -> None:
    prompt = PromptService().build_skin_task_prompt(
        issues_str="痘痘、黑头",
        skin_type_name="油性皮肤",
    )

    assert "油性皮肤" in prompt
    assert "痘痘、黑头" in prompt
    assert '{"task": "任务描述"}' in prompt
