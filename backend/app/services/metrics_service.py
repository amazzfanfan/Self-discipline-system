from __future__ import annotations

import logging
import time
from datetime import datetime

from app.core.time import local_today
from app.services.cache_service import _get_redis, get_background_worker_status


logger = logging.getLogger(__name__)
LATENCY_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 120000)


def _daily_key(now: datetime | None = None) -> str:
    day = now.date() if now else local_today()
    return f"system-agent:metrics:{day.isoformat()}"


async def increment_metric(name: str, amount: int = 1) -> None:
    try:
        client = _get_redis()
        key = _daily_key()
        async with client.pipeline(transaction=False) as pipeline:
            pipeline.hincrby(key, name[:180], amount)
            pipeline.expire(key, 3 * 24 * 60 * 60)
            await pipeline.execute()
    except Exception as exc:
        logger.debug("Metric increment failed: %s", exc)


async def observe_http_request(route: str, status_code: int, duration_ms: float) -> None:
    try:
        client = _get_redis()
        key = _daily_key()
        status_group = f"{status_code // 100}xx"
        route_name = route.replace(":", "_")[:100]
        bucket = next((item for item in LATENCY_BUCKETS_MS if duration_ms <= item), 120000)
        async with client.pipeline(transaction=False) as pipeline:
            pipeline.hincrby(key, "http:requests", 1)
            pipeline.hincrby(key, f"http:status:{status_group}", 1)
            pipeline.hincrby(key, f"http:route:{route_name}", 1)
            pipeline.hincrby(key, f"http:latency_bucket:{bucket}", 1)
            pipeline.hincrbyfloat(key, "http:duration_sum_ms", duration_ms)
            pipeline.expire(key, 3 * 24 * 60 * 60)
            await pipeline.execute()
    except Exception as exc:
        logger.debug("HTTP metric observation failed: %s", exc)


async def observe_external_call(
    kind: str,
    status: str,
    duration_ms: float,
    *,
    tokens: int = 0,
) -> None:
    try:
        client = _get_redis()
        key = _daily_key()
        safe_kind = kind[:40]
        bucket = next((item for item in LATENCY_BUCKETS_MS if duration_ms <= item), 120000)
        async with client.pipeline(transaction=False) as pipeline:
            pipeline.hincrby(key, f"external:{safe_kind}:calls", 1)
            pipeline.hincrby(key, f"external:{safe_kind}:status:{status[:30]}", 1)
            pipeline.hincrby(key, f"external:{safe_kind}:latency_bucket:{bucket}", 1)
            pipeline.hincrbyfloat(key, f"external:{safe_kind}:duration_sum_ms", duration_ms)
            pipeline.hincrby(key, f"external:{safe_kind}:tokens", max(0, tokens))
            pipeline.expire(key, 3 * 24 * 60 * 60)
            await pipeline.execute()
    except Exception as exc:
        logger.debug("External metric observation failed: %s", exc)


def _histogram_percentile(values: dict[str, str], percentile: float) -> int | None:
    counts = [int(values.get(f"http:latency_bucket:{bucket}", 0)) for bucket in LATENCY_BUCKETS_MS]
    total = sum(counts)
    if total <= 0:
        return None
    target = max(1, int(total * percentile + 0.999))
    seen = 0
    for bucket, count in zip(LATENCY_BUCKETS_MS, counts):
        seen += count
        if seen >= target:
            return bucket
    return LATENCY_BUCKETS_MS[-1]


async def metrics_snapshot() -> dict:
    client = _get_redis()
    values = await client.hgetall(_daily_key())
    requests = int(values.get("http:requests", 0))
    duration_sum = float(values.get("http:duration_sum_ms", 0.0))
    counters = {}
    for key, value in values.items():
        if key.startswith("http:latency_bucket:") or key == "http:duration_sum_ms":
            continue
        try:
            counters[key] = int(value)
        except ValueError:
            counters[key] = round(float(value), 2)
    now_ms = int(time.time() * 1000)
    capacity = {}
    for kind in ("llm", "embedding", "faceplus"):
        capacity[kind] = int(
            await client.zcount(f"system-agent:capacity:{kind}", now_ms, "+inf")
        )
    budget_raw = await client.hgetall(
        f"system-agent:ai-budget:global:{local_today().isoformat()}"
    )
    return {
        "date": local_today().isoformat(),
        "http": {
            "requests": requests,
            "average_ms": round(duration_sum / requests, 2) if requests else None,
            "p50_bucket_ms": _histogram_percentile(values, 0.50),
            "p95_bucket_ms": _histogram_percentile(values, 0.95),
            "p99_bucket_ms": _histogram_percentile(values, 0.99),
        },
        "counters": counters,
        "capacity": capacity,
        "ai_budget": {
            "calls": int(budget_raw.get("calls", 0)),
            "tokens": int(budget_raw.get("tokens", 0)),
        },
        "worker": await get_background_worker_status(),
    }
