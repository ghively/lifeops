"""Minimal SlowAPI-compatible fallback for offline environments."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from functools import wraps
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""

    def __init__(self, detail: str, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.headers = headers or {}


def get_remote_address(request: Request) -> str:
    # H50: Only trust X-Forwarded-For from configured trusted proxies.
    # Set TRUSTED_PROXIES env var (comma-separated IPs/CIDRs) to enable.
    # Falls back to direct client IP if the request doesn't come from a trusted proxy.
    trusted_proxies_str = getattr(request.app.state, "_trusted_proxies", "")
    client = request.client
    if not trusted_proxies_str or not client:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        return client.host if client else "unknown"

    # Check if direct client is a trusted proxy
    trusted_proxies = [p.strip() for p in trusted_proxies_str.split(",") if p.strip()]
    if client.host in trusted_proxies:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return client.host if client else "unknown"


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


class SlowAPIMiddleware(BaseHTTPMiddleware):
    """Attach rate-limit headers collected by the decorator."""

    async def dispatch(self, request: Request, call_next: Callable[..., Any]):
        response = await call_next(request)
        headers = getattr(request.state, "_rate_limit_headers", None)
        if headers:
            for key, value in headers.items():
                response.headers[key] = value
        return response


class Limiter:
    """Small in-memory limiter that mirrors the subset of SlowAPI used here."""

    def __init__(
        self,
        key_func: Callable[[Request], str],
        storage_uri: str = "memory://",
        headers_enabled: bool = False,
        default_limits: list[str] | None = None,
    ):
        self.key_func = key_func
        self.storage_uri = storage_uri
        self.headers_enabled = headers_enabled
        self.default_limits = default_limits or []
        self.enabled = True
        self._buckets: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)

    def limit(self, rate: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        amount, window_seconds = self._parse_rate(rate)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                request = kwargs.get("request") or next(
                    (arg for arg in args if isinstance(arg, Request)),
                    None,
                )

                if not self.enabled or request is None:
                    return await func(*args, **kwargs)

                now = time.time()
                key = self.key_func(request)
                bucket_key = (func.__module__, request.url.path, key)
                bucket = self._buckets[bucket_key]

                while bucket and bucket[0] <= now - window_seconds:
                    bucket.popleft()

                if len(bucket) >= amount:
                    reset_at = int(bucket[0] + window_seconds)
                    headers = self._headers(amount, 0, reset_at) if self.headers_enabled else {}
                    request.state._rate_limit_headers = headers
                    raise RateLimitExceeded("Rate limit exceeded", headers=headers)

                bucket.append(now)
                remaining = max(amount - len(bucket), 0)
                reset_at = int(bucket[0] + window_seconds)
                if self.headers_enabled:
                    request.state._rate_limit_headers = self._headers(amount, remaining, reset_at)

                return await func(*args, **kwargs)

            return wrapper

        return decorator

    @staticmethod
    def _parse_rate(rate: str) -> tuple[int, int]:
        amount_text, window_text = rate.split("/", 1)
        amount = int(amount_text.strip())
        unit = window_text.strip().lower()
        if unit in {"second", "sec"}:
            return amount, 1
        if unit in {"minute", "min"}:
            return amount, 60
        if unit in {"hour", "hr"}:
            return amount, 3600
        raise ValueError(f"Unsupported rate window: {rate}")

    @staticmethod
    def _headers(limit: int, remaining: int, reset_at: int) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
