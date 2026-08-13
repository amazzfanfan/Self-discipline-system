"""
LLM Service - 统一的 LLM 调用接口
使用 LiteLLM 提供统一的 API，支持重试、流式输出、向量嵌入等功能
"""

import litellm
from litellm import acompletion
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.services.ai_budget_service import (
    AIBudgetExceeded,
    reserve_ai_budget,
    settle_ai_budget,
)
from app.services.capacity_service import (
    CapacityExceeded,
    CapacityUnavailable,
    distributed_capacity,
)
from typing import AsyncGenerator
import logging
import time
from contextvars import ContextVar

from opentelemetry import trace
from app.services.metrics_service import increment_metric, observe_external_call

logger = logging.getLogger(__name__)
settings = get_settings()
tracer = trace.get_tracer("system-agent.llm")
_usage_context: ContextVar[dict | None] = ContextVar("llm_usage", default=None)
_user_context: ContextVar[str | None] = ContextVar("llm_user", default=None)


def begin_llm_metrics(user_id: str | None = None) -> None:
    _user_context.set(user_id)
    _usage_context.set({
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0.0,
        "models": [],
        "llm_calls": 0,
    })


def get_llm_metrics() -> dict:
    return dict(_usage_context.get() or {})


def _record_usage(response, model: str) -> None:
    metrics = _usage_context.get()
    if metrics is None:
        return
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    hidden = getattr(response, "_hidden_params", {}) or {}
    cost = float(hidden.get("response_cost", 0.0) or 0.0)
    metrics["input_tokens"] += input_tokens
    metrics["output_tokens"] += output_tokens
    metrics["estimated_cost"] = round(metrics["estimated_cost"] + cost, 6)
    if model not in metrics["models"]:
        metrics["models"].append(model)


def _usage_tokens(response) -> int:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or 0)
    return total or prompt + completion


def _estimated_chat_tokens(messages: list[dict], max_tokens: int) -> int:
    # UTF-8 byte length is intentionally conservative for mixed Chinese/English
    # prompts and prevents the preflight budget reservation from undercounting.
    input_bytes = sum(
        len(str(item.get("content", "")).encode("utf-8")) for item in messages
    )
    return max(1, input_bytes) + max(1, max_tokens)


def _record_call(model: str) -> None:
    metrics = _usage_context.get()
    if metrics is None:
        return
    metrics["llm_calls"] += 1
    if model not in metrics["models"]:
        metrics["models"].append(model)

# 配置 LiteLLM
litellm.num_retries = settings.LLM_MAX_RETRIES
litellm.request_timeout = settings.LLM_TIMEOUT
litellm.drop_params = True  # 忽略不支持的参数


async def chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    response_format: dict = None,
    api_key: str = None,
    base_url: str = None,
    enable_thinking: bool | None = None,
    num_retries: int | None = None,
    timeout: float | None = None,
) -> str:
    """
    统一的 LLM 调用接口
    
    Args:
        messages: 消息列表
        model: 模型名称（可选，默认使用配置的模型）
        temperature: 温度参数（可选）
        max_tokens: 最大 token 数（可选）
        response_format: 响应格式（可选，如 JSON）
        api_key: API Key（可选，默认使用主模型的 API Key）
        base_url: Base URL（可选，默认使用主模型的 Base URL）
    
    Returns:
        AI 回复内容
    """
    model = model or settings.chat_model
    temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
    max_tokens = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
    api_key = api_key or settings.AI_API_KEY
    base_url = base_url or settings.AI_BASE_URL
    if not api_key:
        raise RuntimeError("AI_API_KEY is not configured")
    
    try:
        # 构建 litellm 模型名称
        # 如果是自定义 API，使用 openai/ 前缀
        if base_url and "openai" not in model.lower():
            litellm_model = f"openai/{model}"
        else:
            litellm_model = model
        
        kwargs = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": api_key,
            "api_base": base_url,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if enable_thinking is not None:
            kwargs["extra_body"] = {"enable_thinking": enable_thinking}
        if num_retries is not None:
            kwargs["num_retries"] = num_retries
        if timeout is not None:
            kwargs["timeout"] = timeout
        
        logger.info(f"Calling LLM: model={model}, base_url={base_url}, messages={len(messages)}")
        _record_call(model)
        async with distributed_capacity("llm", settings.AI_MAX_CONCURRENCY):
            reservation = await reserve_ai_budget(
                _user_context.get(),
                _estimated_chat_tokens(messages, max_tokens),
            )
            with tracer.start_as_current_span("gen_ai.chat") as span:
                span.set_attribute("gen_ai.request.model", model)
                span.set_attribute("gen_ai.operation.name", "chat")
                provider_started = time.perf_counter()
                response = await acompletion(**kwargs)
                _record_usage(response, model)
                await observe_external_call(
                    "llm",
                    "success",
                    (time.perf_counter() - provider_started) * 1000,
                    tokens=_usage_tokens(response),
                )
            await settle_ai_budget(reservation, _usage_tokens(response))
        
        content = response.choices[0].message.content
        logger.info(f"LLM response received: {len(content)} chars")
        
        return content
        
    except litellm.RateLimitError as e:
        await increment_metric("external:llm:rate_limited")
        logger.warning(f"Rate limit hit: {e}")
        raise
    except litellm.APIError as e:
        await increment_metric("external:llm:api_error")
        logger.error(f"API error: {e}")
        raise
    except Exception as e:
        await increment_metric("external:llm:error")
        logger.error(f"LLM call failed: {e}")
        raise


async def chat_completion_stream(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    api_key: str = None,
    base_url: str = None,
    enable_thinking: bool | None = None,
    num_retries: int | None = None,
    timeout: float | None = None,
) -> AsyncGenerator[str, None]:
    """
    流式 LLM 调用

    Args:
        messages: 消息列表
        model: 模型名称（可选）
        temperature: 温度参数（可选）
        max_tokens: 最大 token 数（可选）
        api_key: API Key（可选）
        base_url: Base URL（可选）

    Yields:
        AI 回复的内容块
    """
    model = model or settings.chat_model
    temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
    max_tokens = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
    api_key = api_key or settings.AI_API_KEY
    base_url = base_url or settings.AI_BASE_URL
    if not api_key:
        raise RuntimeError("AI_API_KEY is not configured")

    # 构建 litellm 模型名称
    if base_url and "openai" not in model.lower():
        litellm_model = f"openai/{model}"
    else:
        litellm_model = model

    try:
        logger.info(f"Calling LLM (stream): model={model}")
        _record_call(model)

        kwargs = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "api_key": api_key,
            "api_base": base_url,
        }
        if enable_thinking is not None:
            kwargs["extra_body"] = {"enable_thinking": enable_thinking}
        if num_retries is not None:
            kwargs["num_retries"] = num_retries
        if timeout is not None:
            kwargs["timeout"] = timeout

        async with distributed_capacity("llm", settings.AI_MAX_CONCURRENCY):
            reservation = await reserve_ai_budget(
                _user_context.get(),
                _estimated_chat_tokens(messages, max_tokens),
            )
            actual_tokens = 0
            provider_started = time.perf_counter()
            response = await acompletion(**kwargs)

            async for chunk in response:
                _record_usage(chunk, model)
                actual_tokens = max(actual_tokens, _usage_tokens(chunk))
                content = chunk.choices[0].delta.content
                if content:
                    yield content
            await observe_external_call(
                "llm_stream",
                "success",
                (time.perf_counter() - provider_started) * 1000,
                tokens=actual_tokens,
            )
            await settle_ai_budget(reservation, actual_tokens)

    except Exception as e:
        await increment_metric("external:llm_stream:error")
        logger.error(f"Stream LLM call failed: {e}")
        raise


async def get_embedding(
    text: str,
    model: str = None
) -> list[float]:
    """
    获取文本的向量嵌入
    
    Args:
        text: 输入文本
        model: 嵌入模型名称（可选）
    
    Returns:
        向量嵌入列表
    """
    model = model or settings.EMBEDDING_MODEL
    
    try:
        # 使用 OpenAI 兼容 API 获取嵌入
        embedding_api_key = settings.EMBEDDING_API_KEY or settings.AI_API_KEY
        if not embedding_api_key:
            raise RuntimeError("EMBEDDING_API_KEY or AI_API_KEY is not configured")
        client = AsyncOpenAI(
            api_key=embedding_api_key,
            base_url=settings.EMBEDDING_BASE_URL or settings.AI_BASE_URL,
        )
        
        logger.info(f"Getting embedding for text: {len(text)} chars")
        
        async with distributed_capacity("embedding", settings.EMBEDDING_MAX_CONCURRENCY):
            reservation = await reserve_ai_budget(
                _user_context.get(),
                max(1, len(text.encode("utf-8"))),
            )
            provider_started = time.perf_counter()
            response = await client.embeddings.create(
                model=model,
                input=text,
                dimensions=settings.EMBEDDING_DIMENSION,
                encoding_format="float",
            )
            await observe_external_call(
                "embedding",
                "success",
                (time.perf_counter() - provider_started) * 1000,
                tokens=_usage_tokens(response),
            )
            await settle_ai_budget(reservation, _usage_tokens(response))
        
        embedding = response.data[0].embedding
        logger.info(f"Embedding received: dimension={len(embedding)}")
        
        return embedding
        
    except Exception as e:
        await increment_metric("external:embedding:error")
        logger.error(f"Embedding failed: {e}")
        raise


async def chat_completion_with_fallback(
    messages: list[dict],
    primary_model: str = None,
    fallback_model: str = None,
    **kwargs
) -> str:
    """
    带降级的 LLM 调用
    
    Args:
        messages: 消息列表
        primary_model: 主模型（可选）
        fallback_model: 备用模型（可选）
        **kwargs: 其他参数
    
    Returns:
        AI 回复内容
    """
    primary_model = primary_model or settings.chat_model
    fallback_model = fallback_model or settings.LLM_FALLBACK_MODEL
    
    try:
        # 尝试主模型
        return await chat_completion(
            messages, 
            model=primary_model,
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
            **kwargs
        )
    except Exception as e:
        if isinstance(e, (AIBudgetExceeded, CapacityExceeded, CapacityUnavailable)):
            raise
        if not fallback_model:
            raise
        logger.warning(f"Primary model failed: {e}, trying fallback")
        try:
            # 降级到备用模型
            return await chat_completion(
                messages, 
                model=fallback_model,
                api_key=settings.LLM_FALLBACK_API_KEY,
                base_url=settings.LLM_FALLBACK_BASE_URL,
                **kwargs
            )
        except Exception as e2:
            logger.error(f"Fallback model also failed: {e2}")
            raise Exception("所有模型均不可用，主模型和备用模型都调用失败")


async def chat_completion_stream_with_fallback(
    messages: list[dict],
    primary_model: str = None,
    fallback_model: str = None,
    **kwargs,
) -> AsyncGenerator[str, None]:
    """Stream from the primary model and fail over only before any content is emitted."""
    primary_model = primary_model or settings.chat_model
    fallback_model = fallback_model if fallback_model is not None else settings.LLM_FALLBACK_MODEL
    emitted = False
    try:
        async for chunk in chat_completion_stream(
            messages,
            model=primary_model,
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
            **kwargs,
        ):
            emitted = True
            yield chunk
        return
    except Exception as primary_error:
        if isinstance(primary_error, (AIBudgetExceeded, CapacityExceeded, CapacityUnavailable)):
            raise
        if emitted or not fallback_model:
            raise
        logger.warning(f"Primary stream failed before first token: {primary_error}, trying fallback")

    async for chunk in chat_completion_stream(
        messages,
        model=fallback_model,
        api_key=settings.LLM_FALLBACK_API_KEY or settings.AI_API_KEY,
        base_url=settings.LLM_FALLBACK_BASE_URL or settings.AI_BASE_URL,
        **kwargs,
    ):
        yield chunk


class LLMChatAdapter:
    """Small adapter used by services that expect an async ``chat`` client."""

    async def chat(self, messages: list[dict]) -> str:
        return await chat_completion_with_fallback(
            messages=messages,
            temperature=0,
            max_tokens=400,
            response_format={"type": "json_object"},
            enable_thinking=False,
            num_retries=0,
            timeout=20,
        )

