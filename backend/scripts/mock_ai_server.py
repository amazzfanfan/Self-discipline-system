"""OpenAI-compatible local upstream used by concurrency/load tests.

Run:
    python -m uvicorn scripts.mock_ai_server:app --port 9001

Then point AI_BASE_URL and EMBEDDING_BASE_URL at http://127.0.0.1:9001/v1.
No external model or paid API is contacted.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse


app = FastAPI(title="System Agent Mock AI")
_active = 0
_peak_active = 0
_requests = 0
_active_lock = asyncio.Lock()


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default)


async def _enter() -> None:
    global _active, _peak_active, _requests
    async with _active_lock:
        limit = max(1, int(_setting("MOCK_AI_MAX_CONCURRENCY", "100")))
        if _active >= limit:
            raise HTTPException(429, "mock upstream concurrency exceeded")
        _active += 1
        _peak_active = max(_peak_active, _active)
        _requests += 1


async def _leave() -> None:
    global _active
    async with _active_lock:
        _active = max(0, _active - 1)


def _content(body: dict) -> str:
    serialized = json.dumps(body.get("messages", []), ensure_ascii=False)
    if "available_tools" in serialized:
        return json.dumps(
            {"action": "respond", "reason": "mock pressure-test response"},
            ensure_ascii=False,
        )
    return "这是本地 Mock AI 回复，不会产生任何外部模型费用。"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active": _active,
        "peak_active": _peak_active,
        "requests": _requests,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    await _enter()
    body = await request.json()
    delay = max(0, int(_setting("MOCK_AI_DELAY_MS", "300"))) / 1000
    error_rate = min(1.0, max(0.0, float(_setting("MOCK_AI_ERROR_RATE", "0"))))
    if random.random() < error_rate:
        await _leave()
        raise HTTPException(503, "mock upstream failure")
    content = _content(body)
    model = body.get("model", "mock-model")
    request_id = f"chatcmpl-{uuid.uuid4().hex}"

    if not body.get("stream"):
        try:
            await asyncio.sleep(delay)
            return {
                "id": request_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 16,
                    "total_tokens": 36,
                },
            }
        finally:
            await _leave()

    async def events():
        try:
            await asyncio.sleep(delay)
            chunks = [content[index:index + 8] for index in range(0, len(content), 8)]
            for chunk in chunks:
                payload = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            final = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 16, "total_tokens": 36},
            }
            yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            await _leave()

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    await _enter()
    try:
        body = await request.json()
        await asyncio.sleep(max(0, int(_setting("MOCK_AI_DELAY_MS", "300"))) / 1000)
        dimensions = min(4096, max(1, int(body.get("dimensions", 1536))))
        return {
            "object": "list",
            "model": body.get("model", "mock-embedding"),
            "data": [{"object": "embedding", "index": 0, "embedding": [0.0] * dimensions}],
            "usage": {"prompt_tokens": 8, "total_tokens": 8},
        }
    finally:
        await _leave()
