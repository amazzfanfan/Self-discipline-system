"""Safe AI concurrency probe for the local OpenAI-compatible mock server.

Example (PowerShell):
    $env:AI_BASE_URL='http://127.0.0.1:9010/v1'
    $env:AI_API_KEY='mock'
    $env:AI_MAX_CONCURRENCY='3'
    $env:AI_BUDGET_ENFORCEMENT='false'
    python -m scripts.ai_gate_probe --requests 12 --concurrency 12

Remote model URLs are rejected so this command cannot consume paid quota.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from urllib.parse import urlparse

from app.core.config import get_settings
from app.services.llm_service import begin_llm_metrics, chat_completion


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return ordered[index]


async def run(requests: int, concurrency: int) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    durations: list[float] = []
    errors: dict[str, int] = {}

    async def one(index: int) -> None:
        async with semaphore:
            begin_llm_metrics(f"mock-probe-{index}")
            started = time.perf_counter()
            try:
                await chat_completion(
                    [{"role": "user", "content": f"mock concurrency probe {index}"}],
                    max_tokens=32,
                    num_retries=0,
                )
            except Exception as exc:
                cause = exc.__cause__
                detail = f": {type(cause).__name__}" if cause else ""
                name = f"{type(exc).__name__}{detail}"
                errors[name] = errors.get(name, 0) + 1
            durations.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one(index) for index in range(requests)))
    wall = time.perf_counter() - started
    completed = requests - sum(errors.values())
    return {
        "requests": requests,
        "client_concurrency": concurrency,
        "configured_gate": get_settings().AI_MAX_CONCURRENCY,
        "completed": completed,
        "errors": errors,
        "wall_seconds": round(wall, 3),
        "requests_per_second": round(requests / wall, 2),
        "average_ms": round(statistics.mean(durations), 2),
        "p95_ms": round(_percentile(durations, 0.95), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--concurrency", type=int, default=12)
    args = parser.parse_args()
    settings = get_settings()
    target = urlparse(settings.AI_BASE_URL)
    if target.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("AI_BASE_URL must point to a loopback Mock AI server")
    result = asyncio.run(run(max(1, args.requests), max(1, args.concurrency)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    main()
