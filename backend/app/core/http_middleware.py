from __future__ import annotations

import json
import time

from app.core.config import get_settings
from app.services.metrics_service import observe_http_request


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self.max_bytes = get_settings().MAX_REQUEST_BODY_MB * 1024 * 1024

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        try:
            too_large = raw_length is not None and int(raw_length) > self.max_bytes
        except ValueError:
            too_large = True
        if not too_large:
            received = 0
            response_started = False

            async def limited_receive():
                nonlocal received
                message = await receive()
                if message.get("type") == "http.request":
                    received += len(message.get("body", b""))
                    if received > self.max_bytes:
                        raise RequestBodyTooLarge
                return message

            async def track_send(message):
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                await send(message)

            try:
                await self.app(scope, limited_receive, track_send)
                return
            except RequestBodyTooLarge:
                if response_started:
                    raise
        payload = json.dumps({"detail": "Request body too large"}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": payload})


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
        self.settings = get_settings()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.settings.SECURITY_HEADERS_ENABLED:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                additions = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"camera=(self), microphone=(), geolocation=()",
                    b"content-security-policy": (
                        b"default-src 'self'; base-uri 'self'; object-src 'none'; "
                        b"frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                        b"connect-src 'self' ws: wss:"
                    ),
                }
                if self.settings.ENVIRONMENT.lower() == "production":
                    additions[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                existing = {key.lower() for key, _ in headers}
                headers.extend((key, value) for key, value in additions.items() if key not in existing)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_code = 500

        async def capture_status(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            route = scope.get("route")
            route_path = getattr(route, "path", None) or "<unmatched>"
            duration_ms = (time.perf_counter() - started) * 1000
            await observe_http_request(str(route_path), status_code, duration_ms)
