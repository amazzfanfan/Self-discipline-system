import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.client_ip import get_client_ip
from app.core.http_middleware import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import ip_rate_limit_key, user_or_ip_rate_limit_key
from app.core.security import create_access_token
from app.modules.chat import router as chat_router
from app.services import ai_budget_service, capacity_service, metrics_service


def make_request(peer: str, headers: dict[str, str] | None = None) -> Request:
    encoded = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": encoded,
        "client": (peer, 12345),
        "server": ("testserver", 80),
    })


def test_trusted_proxy_chain_uses_rightmost_untrusted_address():
    request = make_request(
        "127.0.0.1",
        {"X-Forwarded-For": "198.51.100.99, 203.0.113.7"},
    )

    assert get_client_ip(request) == "203.0.113.7"
    assert ip_rate_limit_key(request) == "ip:203.0.113.7"


def test_untrusted_peer_cannot_spoof_forwarded_address():
    request = make_request(
        "203.0.113.9",
        {"X-Forwarded-For": "198.51.100.99"},
    )

    assert get_client_ip(request) == "203.0.113.9"


def test_real_ip_header_is_not_used_as_an_unverified_fallback():
    request = make_request(
        "127.0.0.1",
        {"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "198.51.100.99"},
    )

    assert get_client_ip(request) == "127.0.0.1"


def test_authenticated_rate_key_is_user_scoped():
    token = create_access_token({"sub": "user-123"})
    request = make_request("127.0.0.1", {"Authorization": f"Bearer {token}"})

    assert user_or_ip_rate_limit_key(request) == "user:user-123"


def test_security_headers_are_added():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    async def root():
        return {"ok": True}

    response = TestClient(app).get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_declared_oversized_request_is_rejected_before_route_execution():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware)

    @app.post("/")
    async def root():
        return {"ok": True}

    response = TestClient(app).post(
        "/",
        headers={"Content-Length": str(41 * 1024 * 1024)},
    )

    assert response.status_code == 413


def test_chunked_oversized_request_is_counted_while_streaming():
    sent = []
    incoming = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"56", "more_body": False},
    ]

    async def downstream(_scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def execute():
        middleware = RequestBodyLimitMiddleware(downstream)
        middleware.max_bytes = 5

        async def receive():
            return incoming.pop(0)

        async def send(message):
            sent.append(message)

        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [],
            },
            receive,
            send,
        )

    asyncio.run(execute())

    assert sent[0]["status"] == 413


def test_capacity_lease_is_released(monkeypatch):
    client = MagicMock()
    client.eval = AsyncMock(return_value=1)
    client.zrem = AsyncMock()
    monkeypatch.setattr(capacity_service, "_get_redis", lambda: client)
    monkeypatch.setattr(capacity_service, "increment_metric", AsyncMock())

    async def execute():
        async with capacity_service.distributed_capacity("llm", 2, wait_seconds=0):
            pass

    asyncio.run(execute())

    client.eval.assert_awaited_once()
    client.zrem.assert_awaited_once()


def test_capacity_rejection_is_explicit(monkeypatch):
    client = MagicMock()
    client.eval = AsyncMock(return_value=0)
    monkeypatch.setattr(capacity_service, "_get_redis", lambda: client)
    monkeypatch.setattr(capacity_service, "increment_metric", AsyncMock())

    async def execute():
        async with capacity_service.distributed_capacity("llm", 1, wait_seconds=0):
            pass

    with pytest.raises(capacity_service.CapacityExceeded):
        asyncio.run(execute())


def test_ai_budget_rejection_reports_scope(monkeypatch):
    client = MagicMock()
    client.eval = AsyncMock(return_value=3)
    monkeypatch.setattr(ai_budget_service, "_get_redis", lambda: client)
    monkeypatch.setattr(ai_budget_service, "increment_metric", AsyncMock())

    with pytest.raises(ai_budget_service.AIBudgetExceeded) as exc:
        asyncio.run(ai_budget_service.reserve_ai_budget("user-1", 1000))

    assert exc.value.scope == "user"
    assert exc.value.resource == "tokens"


def test_agent_lease_is_released(monkeypatch):
    monkeypatch.setattr(chat_router, "acquire_lock", AsyncMock(return_value="lease-token"))
    release = AsyncMock()
    monkeypatch.setattr(chat_router, "release_lock", release)
    monkeypatch.setattr(chat_router, "renew_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(chat_router, "increment_metric", AsyncMock())

    async def execute():
        lease = await chat_router._start_agent_lease("user-1")
        await chat_router._finish_agent_lease(lease)

    asyncio.run(execute())

    release.assert_awaited_once_with("agent-execution:user-1", "lease-token")


def test_histogram_percentile_uses_bucket_boundaries():
    values = {
        "http:latency_bucket:50": "5",
        "http:latency_bucket:250": "4",
        "http:latency_bucket:1000": "1",
    }

    assert metrics_service._histogram_percentile(values, 0.50) == 50
    assert metrics_service._histogram_percentile(values, 0.95) == 1000
