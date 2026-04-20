"""Rate-limiting helpers for FastAPI routes.

Uses the built-in in-memory vendor implementation (no external deps).
Compatible with FastAPI 0.109.0 / Starlette 0.35.x.

NOTE (H49): Storage is in-memory only. Production deployments with multiple
replicas should configure a shared backend (e.g. Redis) to ensure rate limits
are enforced consistently across all instances.
"""

from fastapi import Request

from app.vendor.slowapi_compat import Limiter, get_remote_address

# NOTE (H48): Per-IP limiter for unauthenticated / public endpoints.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    headers_enabled=True,
    default_limits=[],
)


def _user_id_key(request: Request) -> str:
    """Key function for per-user rate limiting on authenticated endpoints."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        payload = auth_service.decode_token(token)
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
    # Fall back to IP if no valid token
    return get_remote_address(request)


from app.services.auth import auth_service  # noqa: E402 (needed by _user_id_key)

user_limiter = Limiter(
    key_func=_user_id_key,
    storage_uri="memory://",
    headers_enabled=True,
    default_limits=[],
)

auth_rate_limit = limiter.limit("5/minute")
read_rate_limit = limiter.limit("60/minute")
write_rate_limit = limiter.limit("30/minute")
