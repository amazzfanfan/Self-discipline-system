"""Dependency-light load baseline for safe local and Mock-AI testing."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int(len(ordered) * value))
    return ordered[index]


async def run(args) -> dict:
    semaphore = asyncio.Semaphore(args.concurrency)
    durations: list[float] = []
    statuses: dict[str, int] = {}
    tokens = [args.token] if args.token else []
    if args.tokens_file:
        with open(args.tokens_file, encoding="utf-8") as handle:
            tokens = [line.strip() for line in handle if line.strip()]
    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
    )
    async with httpx.AsyncClient(
        base_url=args.base_url,
        limits=limits,
        timeout=args.timeout,
    ) as client:
        async def one(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    if args.scenario == "health":
                        response = await client.get("/health")
                    elif args.scenario == "ready":
                        response = await client.get("/health/ready")
                    else:
                        token = tokens[0] if args.scenario == "agent-serial" else tokens[index % len(tokens)]
                        response = await client.post(
                            "/api/chat/send",
                            json={"content": f"{args.content} #{index}"},
                            headers={"Authorization": f"Bearer {token}"},
                        )
                    key = str(response.status_code)
                except Exception as exc:
                    key = type(exc).__name__
                durations.append((time.perf_counter() - started) * 1000)
                statuses[key] = statuses.get(key, 0) + 1

        started = time.perf_counter()
        await asyncio.gather(*(one(index) for index in range(args.requests)))
        wall = time.perf_counter() - started

    successes = statuses.get("200", 0)
    accepted = successes
    if args.scenario == "agent-serial":
        accepted += statuses.get("409", 0)
    result = {
        "scenario": args.scenario,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "wall_seconds": round(wall, 3),
        "requests_per_second": round(args.requests / wall, 2),
        "status_counts": statuses,
        "success_rate": round(accepted / args.requests, 4),
        "average_ms": round(statistics.mean(durations), 2),
        "p50_ms": round(percentile(durations, 0.50), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "p99_ms": round(percentile(durations, 0.99), 2),
    }
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--scenario",
        choices=("health", "ready", "chat", "agent-serial"),
        default="health",
    )
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--token", default="")
    parser.add_argument("--tokens-file", default="", help="one access token per line for multi-user chat")
    parser.add_argument("--content", default="请给我一条简短的成长建议")
    parser.add_argument("--max-p95-ms", type=float, default=500)
    parser.add_argument("--min-success-rate", type=float, default=0.99)
    parser.add_argument("--allow-model-calls", action="store_true")
    args = parser.parse_args()
    if args.scenario in {"chat", "agent-serial"} and not (args.token or args.tokens_file):
        parser.error("chat scenarios require --token or --tokens-file")
    if args.scenario in {"chat", "agent-serial"} and not args.allow_model_calls:
        parser.error(
            "chat can call the configured model; point the backend at scripts.mock_ai_server "
            "and pass --allow-model-calls"
        )
    return args


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    passed = (
        result["success_rate"] >= args.min_success_rate
        and result["p95_ms"] <= args.max_p95_ms
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
