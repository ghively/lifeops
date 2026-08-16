"""Rate-limiting helpers for FastAPI routes.

Uses the built-in in-memory vendor implementation (no external deps).
Compatible with FastAPI 0.109.0 / Starlette 0.35.x.

NOTE (H49): Storage is in-memory only. Production deployments with multiple
replicas should configure a shared backend (e.g. Redis) to ensure rate limits
are enforced consistently across all instances.
"""

import json
import logging

from fastapi import Request

from app.vendor.slowapi_compat import Limiter, get_remote_address

logger = logging.getLogger(__name__)

# NOTE (H48): Per-IP limiter for unauthenticated / public endpoints.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    headers_enabled=True,
    default_limits=[],
)


def _user_id_key(request: Request) -> str:
    """Key function for per-user rate limiting on authenticated endpoints.

    On authenticated endpoints the auth dependency runs first, so by the time
    this key function executes the token has already been validated. To make
    sure a malformed-token attacker can't downgrade themselves to the (looser)
    per-IP bucket and dodge per-user limits, we key by IP+token-hash for any
    request whose token is missing or undecodable. That keeps the limit tight
    while still allowing legitimate unauthenticated traffic to be IP-limited.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        payload = auth_service.decode_token(token)
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
        if token:
            # Bad/expired token: bind the bucket to (ip, token-fingerprint) so
            # rotating IPs alone can't reset the counter.
            import hashlib
            fingerprint = hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()[:16]
            return f"badtoken:{get_remote_address(request)}:{fingerprint}"
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


async def _login_key(request: Request) -> str:
    """Key /auth/login by (IP, email) so users behind one NAT don't share a bucket.

    The straight per-IP cap on auth makes /auth/login NAT-hostile — every legit
    user behind a corporate NAT or CGNAT shares one IP and they collectively
    blow through the 5/min limit. Partition the bucket by the email being
    logged in: each user gets their own counter at a given IP.

    Falls back to per-IP if the body can't be parsed or the email is missing,
    so a malformed request can't dodge the limit entirely.

    Caveat: this on its own opens a credential-stuffing window — one IP can
    attempt 5 passwords per minute against any number of emails. The intent
    here is to fix the NAT regression; pairing this with a higher per-IP
    backstop (e.g. stack `@auth_rate_limit` with a relaxed cap) is the
    follow-up if cred-stuffing protection becomes a priority.
    """
    ip = get_remote_address(request)
    try:
        body = await request.body()  # cached on request._body; FastAPI re-reads from the cache
        if body:
            data = json.loads(body)
            email = (data.get("email") or "").strip().lower()
            if email:
                return f"login:{ip}:{email}"
    except (json.JSONDecodeError, ValueError, AttributeError) as exc:
        logger.debug("login rate-limit body parse failed, falling back to per-IP: %s", exc)
    return f"login:{ip}"


login_limiter = Limiter(
    key_func=_login_key,
    storage_uri="memory://",
    headers_enabled=True,
    default_limits=[],
)
login_rate_limit = login_limiter.limit("5/minute")
