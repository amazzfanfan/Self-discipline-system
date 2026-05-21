"""
Cache Service - Redis 缓存服务
提供统一的缓存接口，缓存高频查询数据以减少 DB 和向量计算开销

缓存策略：
- 今日任务: key=tasks:{user_id}:{date}, TTL=到午夜
- 用户评分: key=scores:{user_id}, TTL=5分钟
- 向量搜索: key=memory_search:{user_id}:{query_hash}, TTL=2分钟
"""

import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis 客户端实例（惰性连接，首次使用时建立连接）
redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """获取 Redis 客户端（单例）"""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client


# ─── 底层操作 ────────────────────────────────────────────────────────────


async def get_cached(key: str) -> str | None:
    """获取缓存值，失败时返回 None（不抛异常）"""
    try:
        return await _get_redis().get(key)
    except Exception as e:
        logger.warning(f"Redis get failed for key={key}: {e}")
        return None


async def set_cached(key: str, value: str, ttl: int = 300):
    """设置缓存值，ttl 单位为秒，失败时静默忽略"""
    try:
        await _get_redis().setex(key, ttl, value)
    except Exception as e:
        logger.warning(f"Redis set failed for key={key}: {e}")


async def delete_cached(key: str):
    """删除缓存，失败时静默忽略"""
    try:
        await _get_redis().delete(key)
    except Exception as e:
        logger.warning(f"Redis delete failed for key={key}: {e}")


# ─── 今日任务缓存 ──────────────────────────────────────────────────────


def _tasks_key(user_id: str) -> str:
    """今日任务缓存 key，每天自动隔离"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"tasks:{user_id}:{today}"


def _seconds_until_midnight() -> int:
    """计算距离 UTC 午夜的秒数（作为 TTL）"""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())


async def get_cached_tasks(user_id: str) -> list[dict] | None:
    """获取缓存的今日任务列表，未命中返回 None"""
    raw = await get_cached(_tasks_key(user_id))
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


async def set_cached_tasks(user_id: str, tasks: list[dict]):
    """缓存今日任务列表，TTL 到午夜"""
    ttl = _seconds_until_midnight()
    await set_cached(_tasks_key(user_id), json.dumps(tasks, ensure_ascii=False), ttl)


async def invalidate_tasks(user_id: str):
    """任务变更时清除缓存（完成/跳过/新增任务后调用）"""
    await delete_cached(_tasks_key(user_id))


# ─── 用户评分缓存 ──────────────────────────────────────────────────────


SCORES_TTL = 300  # 5 分钟


def _scores_key(user_id: str) -> str:
    return f"scores:{user_id}"


async def get_cached_scores(user_id: str) -> list[dict] | None:
    """获取缓存的用户评分，未命中返回 None"""
    raw = await get_cached(_scores_key(user_id))
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


async def set_cached_scores(user_id: str, scores: list[dict]):
    """缓存用户评分，TTL 5 分钟"""
    await set_cached(_scores_key(user_id), json.dumps(scores, ensure_ascii=False), SCORES_TTL)


async def invalidate_scores(user_id: str):
    """评分变更时清除缓存（完成/跳过任务后调用）"""
    await delete_cached(_scores_key(user_id))


# ─── 向量搜索缓存 ──────────────────────────────────────────────────────


MEMORY_SEARCH_TTL = 120  # 2 分钟


def _memory_search_key(user_id: str, query: str) -> str:
    """向量搜索缓存 key，基于 query 内容 hash"""
    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
    return f"memory_search:{user_id}:{query_hash}"


async def get_cached_memory_search(user_id: str, query: str) -> list[dict] | None:
    """获取缓存的向量搜索结果，未命中返回 None"""
    raw = await get_cached(_memory_search_key(user_id, query))
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


async def set_cached_memory_search(user_id: str, query: str, results: list[dict]):
    """缓存向量搜索结果，TTL 2 分钟"""
    await set_cached(
        _memory_search_key(user_id, query),
        json.dumps(results, ensure_ascii=False),
        MEMORY_SEARCH_TTL
    )
