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
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.time import local_today, seconds_until_local_midnight

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis 客户端实例（惰性连接，首次使用时建立连接）
redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """获取 Redis 客户端（单例）"""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
        )
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


async def cache_is_ready() -> bool:
    try:
        return bool(await _get_redis().ping())
    except Exception:
        return False


# ─── Refresh sessions ───────────────────────────────────────────────────


def _refresh_session_key(jti: str) -> str:
    return f"auth:refresh:{jti}"


def _user_refresh_set_key(user_id: str) -> str:
    return f"auth:user-refresh:{user_id}"


async def store_refresh_session(jti: str, user_id: str, ttl: int) -> bool:
    """Persist one refresh-token session. Authentication fails closed."""
    try:
        client = _get_redis()
        async with client.pipeline(transaction=True) as pipeline:
            pipeline.set(_refresh_session_key(jti), user_id, ex=ttl)
            pipeline.sadd(_user_refresh_set_key(user_id), jti)
            pipeline.expire(_user_refresh_set_key(user_id), ttl)
            results = await pipeline.execute()
        return bool(results[0])
    except Exception as exc:
        logger.error("Failed to persist refresh session: %s", exc)
        return False


async def consume_refresh_session(jti: str, user_id: str) -> bool:
    """Atomically consume a refresh token so concurrent replay cannot rotate it twice."""
    try:
        client = _get_redis()
        stored = await client.getdel(_refresh_session_key(jti))
        if stored:
            await client.srem(_user_refresh_set_key(stored), jti)
        return stored == user_id
    except Exception as exc:
        logger.error("Failed to consume refresh session: %s", exc)
        return False


async def revoke_refresh_session(jti: str) -> None:
    try:
        client = _get_redis()
        key = _refresh_session_key(jti)
        user_id = await client.get(key)
        await client.delete(key)
        if user_id:
            await client.srem(_user_refresh_set_key(user_id), jti)
    except Exception as exc:
        logger.warning("Failed to revoke refresh session: %s", exc)


async def revoke_all_refresh_sessions(user_id: str) -> None:
    try:
        client = _get_redis()
        set_key = _user_refresh_set_key(user_id)
        session_ids = await client.smembers(set_key)
        keys = [_refresh_session_key(jti) for jti in session_ids]
        if keys:
            await client.delete(*keys)
        await client.delete(set_key)
    except Exception as exc:
        logger.warning("Failed to revoke all refresh sessions: %s", exc)


# ─── Durable background jobs (Redis Stream) ─────────────────────────────


BACKGROUND_JOB_STREAM = "system-agent:jobs"
BACKGROUND_JOB_GROUP = "system-agent-workers"
BACKGROUND_JOB_DEAD_LETTER_STREAM = "system-agent:jobs:dead-letter"
BACKGROUND_JOB_ATTEMPTS_KEY = "system-agent:job-attempts"
BACKGROUND_WORKER_HEARTBEAT_KEY = "system-agent:worker:heartbeat"


async def enqueue_background_job(kind: str, payload: dict) -> str | None:
    try:
        return await _get_redis().xadd(
            BACKGROUND_JOB_STREAM,
            {"kind": kind, "payload": json.dumps(payload, ensure_ascii=False)},
            maxlen=10_000,
            approximate=True,
        )
    except Exception as exc:
        logger.warning("Failed to enqueue background job %s: %s", kind, exc)
        return None


async def enqueue_background_job_once(
    kind: str,
    payload: dict,
    *,
    dedupe_key: str,
    ttl_seconds: int = 60,
) -> str | None:
    """Enqueue once within a short window so status polling cannot create a job storm."""
    marker = f"system-agent:job-dedupe:{dedupe_key}"
    try:
        client = _get_redis()
        acquired = await client.set(marker, "1", ex=ttl_seconds, nx=True)
        if not acquired:
            return "deduplicated"
        try:
            return await client.xadd(
                BACKGROUND_JOB_STREAM,
                {"kind": kind, "payload": json.dumps(payload, ensure_ascii=False)},
                maxlen=10_000,
                approximate=True,
            )
        except Exception:
            await client.delete(marker)
            raise
    except Exception as exc:
        logger.warning("Failed to enqueue deduplicated job %s: %s", kind, exc)
        return None


async def ensure_background_job_group() -> None:
    try:
        await _get_redis().xgroup_create(
            BACKGROUND_JOB_STREAM,
            BACKGROUND_JOB_GROUP,
            id="0",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def read_background_jobs(consumer: str, count: int = 10, block_ms: int = 1000):
    await ensure_background_job_group()
    return await _get_redis().xreadgroup(
        BACKGROUND_JOB_GROUP,
        consumer,
        {BACKGROUND_JOB_STREAM: ">"},
        count=count,
        block=block_ms,
    )


async def claim_stale_background_jobs(
    consumer: str,
    *,
    min_idle_ms: int = 30_000,
    count: int = 10,
) -> list[tuple[str, dict]]:
    """Claim jobs abandoned by a crashed or unhealthy worker."""
    await ensure_background_job_group()
    response = await _get_redis().xautoclaim(
        BACKGROUND_JOB_STREAM,
        BACKGROUND_JOB_GROUP,
        consumer,
        min_idle_time=min_idle_ms,
        start_id="0-0",
        count=count,
    )
    if not response or len(response) < 2:
        return []
    return list(response[1] or [])


async def acknowledge_background_job(message_id: str) -> None:
    client = _get_redis()
    await client.xack(BACKGROUND_JOB_STREAM, BACKGROUND_JOB_GROUP, message_id)
    await client.hdel(BACKGROUND_JOB_ATTEMPTS_KEY, message_id)


async def record_background_job_failure(message_id: str) -> int:
    return int(await _get_redis().hincrby(BACKGROUND_JOB_ATTEMPTS_KEY, message_id, 1))


async def move_background_job_to_dead_letter(
    message_id: str,
    fields: dict,
    *,
    attempts: int,
    error_type: str,
) -> None:
    client = _get_redis()
    await client.xadd(
        BACKGROUND_JOB_DEAD_LETTER_STREAM,
        {
            "original_id": message_id,
            "kind": str(fields.get("kind", "unknown")),
            "payload": str(fields.get("payload", "{}")),
            "attempts": str(attempts),
            "error_type": error_type[:120],
            "failed_at": datetime.now(timezone.utc).isoformat(),
        },
        maxlen=2_000,
        approximate=True,
    )
    await acknowledge_background_job(message_id)


async def set_background_worker_heartbeat(consumer: str, ttl_seconds: int = 20) -> None:
    await _get_redis().set(
        BACKGROUND_WORKER_HEARTBEAT_KEY,
        json.dumps(
            {"consumer": consumer, "seen_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        ),
        ex=ttl_seconds,
    )


async def get_background_worker_status() -> dict:
    """Return worker liveness plus Redis Stream backlog information."""
    try:
        client = _get_redis()
        heartbeat = await client.get(BACKGROUND_WORKER_HEARTBEAT_KEY)
        groups = await client.xinfo_groups(BACKGROUND_JOB_STREAM)
        group = next(
            (item for item in groups if item.get("name") == BACKGROUND_JOB_GROUP),
            {},
        )
        heartbeat_data = json.loads(heartbeat) if heartbeat else {}
        return {
            "ready": bool(heartbeat),
            "consumer": heartbeat_data.get("consumer"),
            "last_seen": heartbeat_data.get("seen_at"),
            "pending": int(group.get("pending", 0) or 0),
            "lag": int(group.get("lag", 0) or 0),
        }
    except Exception as exc:
        logger.warning("Failed to inspect background worker: %s", exc)
        return {
            "ready": False,
            "consumer": None,
            "last_seen": None,
            "pending": None,
            "lag": None,
        }


# ─── 今日任务缓存 ──────────────────────────────────────────────────────


def _tasks_key(user_id: str) -> str:
    """今日任务缓存 key，每天自动隔离"""
    return f"tasks:{user_id}:{local_today().isoformat()}"


def _seconds_until_midnight() -> int:
    """计算距离业务时区午夜的秒数（作为 TTL）。"""
    return seconds_until_local_midnight()


async def acquire_lock(name: str, ttl: int = 300) -> str | None:
    """Return a token when acquired, an empty string when held, or None if Redis is down."""
    token = uuid.uuid4().hex
    try:
        acquired = await _get_redis().set(f"lock:{name}", token, ex=ttl, nx=True)
        return token if acquired else ""
    except Exception as exc:
        logger.warning("Redis lock unavailable for %s: %s", name, exc)
        return None


async def release_lock(name: str, token: str) -> None:
    """Release a lease only when this process still owns it."""
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('del', KEYS[1])
    end
    return 0
    """
    try:
        await _get_redis().eval(script, 1, f"lock:{name}", token)
    except Exception as exc:
        logger.warning("Redis lock release failed for %s: %s", name, exc)


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


# ─── Face++ result cache ───────────────────────────────────────────────


def _skin_analysis_key(image_hash: str, pipeline_version: str) -> str:
    return f"skin_analysis:{pipeline_version}:{image_hash}"


async def get_cached_skin_analysis(image_hash: str, pipeline_version: str) -> dict | None:
    raw = await get_cached(_skin_analysis_key(image_hash, pipeline_version))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_cached_skin_analysis(
    image_hash: str,
    pipeline_version: str,
    result: dict,
) -> None:
    await set_cached(
        _skin_analysis_key(image_hash, pipeline_version),
        json.dumps(result, ensure_ascii=False),
        settings.FACEPLUSPLUS_CACHE_TTL_SECONDS,
    )


# ─── 向量搜索缓存 ──────────────────────────────────────────────────────


MEMORY_SEARCH_TTL = 120  # 2 分钟


def _memory_search_key(
    user_id: str,
    query: str,
    top_k: int = 5,
    memory_type: str | None = None,
    min_importance: float = 0.0,
) -> str:
    """向量搜索缓存 key，基于 query 内容 hash"""
    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
    type_part = memory_type or "all"
    return f"memory_search:{user_id}:{query_hash}:{top_k}:{type_part}:{min_importance:.2f}"


async def get_cached_memory_search(
    user_id: str,
    query: str,
    top_k: int = 5,
    memory_type: str | None = None,
    min_importance: float = 0.0,
) -> list[dict] | None:
    """获取缓存的向量搜索结果，未命中返回 None"""
    raw = await get_cached(
        _memory_search_key(user_id, query, top_k, memory_type, min_importance)
    )
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


async def set_cached_memory_search(
    user_id: str,
    query: str,
    results: list[dict],
    top_k: int = 5,
    memory_type: str | None = None,
    min_importance: float = 0.0,
):
    """缓存向量搜索结果，TTL 2 分钟"""
    await set_cached(
        _memory_search_key(user_id, query, top_k, memory_type, min_importance),
        json.dumps(results, ensure_ascii=False),
        MEMORY_SEARCH_TTL
    )


async def invalidate_memory_search(user_id: str) -> None:
    """Invalidate every cached query variant after memory mutations."""
    try:
        client = _get_redis()
        keys = [key async for key in client.scan_iter(match=f"memory_search:{user_id}:*")]
        if keys:
            await client.delete(*keys)
    except Exception as e:
        logger.warning(f"Redis memory cache invalidation failed: {e}")
