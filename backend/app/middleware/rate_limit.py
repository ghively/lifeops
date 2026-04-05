"""Rate-limiting helpers for FastAPI routes.

Uses the built-in in-memory vendor implementation (no external deps).
Compatible with FastAPI 0.109.0 / Starlette 0.35.x.
"""

from app.vendor.slowapi_compat import Limiter, get_remote_address


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    headers_enabled=True,
    default_limits=[],
)

auth_rate_limit = limiter.limit("5/minute")
read_rate_limit = limiter.limit("60/minute")
write_rate_limit = limiter.limit("30/minute")
