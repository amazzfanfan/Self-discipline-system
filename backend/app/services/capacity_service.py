from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.services.cache_service import _get_redis
from app.services.metrics_service import increment_metric


logger = logging.getLogger(__name__)
settings = get_settings()


class CapacityExceeded(RuntimeError):
    def __init__(self, kind: str):
        super().__init__(f"{kind} capacity is busy")
        self.kind = kind


class CapacityUnavailable(RuntimeError):
    pass


_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, expires, token)
redis.call('EXPIRE', key, math.max(1, math.ceil((expires - now) / 1000)))
return 1
"""


async def _acquire_capacity(kind: str, limit: int, wait_seconds: float) -> str:
    token = uuid.uuid4().hex
    deadline = time.monotonic() + max(0.0, wait_seconds)
    key = f"system-agent:capacity:{kind}"
    while True:
        now_ms = int(time.time() * 1000)
        expires_ms = now_ms + settings.AI_GATE_LEASE_SECONDS * 1000
        try:
            acquired = await _get_redis().eval(
                _ACQUIRE_SCRIPT,
                1,
                key,
                now_ms,
                expires_ms,
                max(1, limit),
                token,
            )
        except Exception as exc:
            await increment_metric(f"capacity:{kind}:unavailable")
            raise CapacityUnavailable("Distributed capacity service unavailable") from exc
        if acquired:
            await increment_metric(f"capacity:{kind}:acquired")
            return token
        if time.monotonic() >= deadline:
            await increment_metric(f"capacity:{kind}:rejected")
            raise CapacityExceeded(kind)
        await asyncio.sleep(0.05)


async def _release_capacity(kind: str, token: str) -> None:
    try:
        await _get_redis().zrem(f"system-agent:capacity:{kind}", token)
    except Exception as exc:
        logger.warning("Failed to release %s capacity lease: %s", kind, exc)


@asynccontextmanager
async def distributed_capacity(
    kind: str,
    limit: int,
    *,
    wait_seconds: float | None = None,
):
    token = await _acquire_capacity(
        kind,
        limit,
        settings.AI_GATE_WAIT_SECONDS if wait_seconds is None else wait_seconds,
    )
    try:
        yield
    finally:
        await _release_capacity(kind, token)
