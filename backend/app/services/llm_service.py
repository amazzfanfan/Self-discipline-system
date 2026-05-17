"""
LLM Service - 统一的 LLM 调用接口
使用 LiteLLM 提供统一的 API，支持重试、流式输出、向量嵌入等功能
"""

import litellm
from litellm import acompletion
from openai import AsyncOpenAI
from app.core.config import get_settings
from typing import AsyncGenerator, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)
settings = get_settings()

# 配置 LiteLLM
litellm.num_retries = settings.LLM_MAX_RETRIES
litellm.request_timeout = settings.LLM_TIMEOUT
litellm.drop_params = True  # 忽略不支持的参数


async def chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    response_format: dict = None
) -> str:
    """
    统一的 LLM 调用接口
    
    Args:
        messages: 消息列表
        model: 模型名称（可选，默认使用配置的模型）
        temperature: 温度参数（可选）
        max_tokens: 最大 token 数（可选）
        response_format: 响应格式（可选，如 JSON）
    
    Returns:
        AI 回复内容
    """
    model = model or settings.chat_model
    temperature = temperature or settings.LLM_TEMPERATURE
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS
    
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        
        logger.info(f"Calling LLM: model={model}, messages={len(messages)}")
        response = await acompletion(**kwargs)
        
        content = response.choices[0].message.content
        logger.info(f"LLM response received: {len(content)} chars")
        
        return content
        
    except litellm.RateLimitError as e:
        logger.warning(f"Rate limit hit: {e}")
        raise
    except litellm.APIError as e:
        logger.error(f"API error: {e}")
        raise
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise


async def chat_completion_stream(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None
) -> AsyncGenerator[str, None]:
    """
    流式 LLM 调用
    
    Args:
        messages: 消息列表
        model: 模型名称（可选）
        temperature: 温度参数（可选）
        max_tokens: 最大 token 数（可选）
    
    Yields:
        AI 回复的内容块
    """
    model = model or settings.chat_model
    temperature = temperature or settings.LLM_TEMPERATURE
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS
    
    try:
        logger.info(f"Calling LLM (stream): model={model}")
        
        response = await acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content
                
    except Exception as e:
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
        client = AsyncOpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
        )
        
        logger.info(f"Getting embedding for text: {len(text)} chars")
        
        response = await client.embeddings.create(
            model=model,
            input=text,
        )
        
        embedding = response.data[0].embedding
        logger.info(f"Embedding received: dimension={len(embedding)}")
        
        return embedding
        
    except Exception as e:
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
        return await chat_completion(messages, model=primary_model, **kwargs)
    except Exception as e:
        logger.warning(f"Primary model failed: {e}, trying fallback")
        try:
            # 降级到备用模型
            return await chat_completion(messages, model=fallback_model, **kwargs)
        except Exception as e2:
            logger.error(f"Fallback model also failed: {e2}")
            # 返回预设回复
            return "抱歉，AI 服务暂时不可用，请稍后再试。"


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    计算文本的 token 数量
    
    Args:
        text: 输入文本
        model: 模型名称（用于选择 tokenizer）
    
    Returns:
        token 数量
    """
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # 简单估算：中文约 1.5 token/字
        return len(text) * 2
