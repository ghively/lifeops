"""Rate-limiting helpers for FastAPI routes."""
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
except ImportError:  # pragma: no cover - used in offline CI/dev environments
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
