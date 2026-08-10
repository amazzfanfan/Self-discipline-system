import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import llm_service


def test_chat_fails_fast_when_api_key_is_missing(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "AI_API_KEY", "")

    with pytest.raises(RuntimeError, match="AI_API_KEY"):
        asyncio.run(
            llm_service.chat_completion(
                [{"role": "user", "content": "hello"}]
            )
        )


def test_embedding_uses_remote_model_and_configured_dimension(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "AI_API_KEY", "chat-key")
    monkeypatch.setattr(llm_service.settings, "EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setattr(
        llm_service.settings,
        "EMBEDDING_BASE_URL",
        "https://example.com/compatible-mode/v1",
    )
    monkeypatch.setattr(llm_service.settings, "EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setattr(llm_service.settings, "EMBEDDING_DIMENSION", 1536)
    client = MagicMock()
    client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1] * 1536)]
        )
    )
    client_cls = MagicMock(return_value=client)
    monkeypatch.setattr(llm_service, "AsyncOpenAI", client_cls)

    result = asyncio.run(llm_service.get_embedding("测试文本"))

    assert len(result) == 1536
    client_cls.assert_called_once_with(
        api_key="embedding-key",
        base_url="https://example.com/compatible-mode/v1",
    )
    client.embeddings.create.assert_awaited_once_with(
        model="text-embedding-v4",
        input="测试文本",
        dimensions=1536,
        encoding_format="float",
    )


def test_chat_can_disable_thinking_and_override_retry_budget(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "AI_API_KEY", "test-key")
    completion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"task":"散步"}'))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            _hidden_params={},
        )
    )
    monkeypatch.setattr(llm_service, "acompletion", completion)

    result = asyncio.run(
        llm_service.chat_completion(
            [{"role": "user", "content": "task"}],
            response_format={"type": "json_object"},
            enable_thinking=False,
            num_retries=0,
            timeout=20,
        )
    )

    assert result == '{"task":"散步"}'
    kwargs = completion.await_args.kwargs
    assert kwargs["extra_body"] == {"enable_thinking": False}
    assert kwargs["num_retries"] == 0
    assert kwargs["timeout"] == 20
