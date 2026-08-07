"""In-memory per-IP rate limiting for the local dashboard API.

The dashboard runs localhost-only and every ``/api/v1/*`` route already
requires authentication, so this is defense-in-depth: a guardrail against
brute-force on the unauthenticated auth endpoints and against runaway
polling. State is per-``RateLimiter`` instance (per app), so a restart or a
fresh test app resets it.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

DEFAULT_LIMIT_PER_MIN = int(os.environ.get("CAREER_API_RATE_LIMIT_PER_MIN", "600"))
AUTH_LIMIT_PER_MIN = int(os.environ.get("CAREER_API_AUTH_RATE_LIMIT_PER_MIN", "10"))
WINDOW_SECONDS = 60.0

_EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Any], Callable[..., Any]], Awaitable[None]
]


class RateLimiter:
    """Sliding-window limiter keyed by client IP + request group."""

    def __init__(
        self,
        default_limit: int = DEFAULT_LIMIT_PER_MIN,
        auth_limit: int = AUTH_LIMIT_PER_MIN,
        window_seconds: float = WINDOW_SECONDS,
    ) -> None:
        self._default_limit = default_limit
        self._auth_limit = auth_limit
        self._window = window_seconds
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    @staticmethod
    def _group(path: str) -> str:
        if path.startswith("/api/v1/auth/"):
            return "auth"
        return "general"

    def allow(self, ip: str, path: str) -> int | None:
        """Return ``None`` when allowed, else seconds until the bucket resets."""
        limit = self._auth_limit if self._group(path) == "auth" else self._default_limit
        bucket = self._hits[(ip, self._group(path))]
        now = time.monotonic()
        cutoff = now - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return max(1, int(self._window - (now - bucket[0])))
        bucket.append(now)
        return None


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, limiter: RateLimiter | None = None) -> None:
        self.app = app
        self.limiter = limiter or RateLimiter()

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith(_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return
        client = scope.get("client") or (None, None)
        ip = client[0] or "unknown"
        retry_after = self.limiter.allow(ip, path)
        if retry_after is None:
            await self.app(scope, receive, send)
            return
        payload = json.dumps({"detail": "Too many requests"}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
            (b"retry-after", str(retry_after).encode("ascii")),
        ]
        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": payload})
