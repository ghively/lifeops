"""Thin HTTP client for the LifeOps memory API.

BUILD_SPEC §43: this plugin is a protocol adapter. Every method here maps
one-to-one onto the LifeOps HTTP memory API; there is no local storage and no
second domain model. Memory lives in LifeOps (NornicDB), not in the plugin.

Client identity is declared with the ``X-LifeOps-Client`` header, the same
mechanism LifeOps Core's HTTP API uses (``get_client`` in
``core/lifeops/api/http.py``). The plugin identifies as ``hermes-personal``,
matching the MCP launch identity.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_CLIENT_ID = "hermes-personal"
API_PREFIX = "/api/v1"
CLIENT_HEADER = "X-LifeOps-Client"

# Source types from BUILD_SPEC §45. External/model-observed content creates
# evidence, not user authority (§46) — automatic sync never claims
# ``user_explicit``.
SOURCE_TYPES = (
    "user_explicit",
    "user_inferred",
    "conversation",
    "email",
    "calendar",
    "document",
    "website",
    "phone_call",
    "system",
    "agent",
)

# §47: memory must never store secrets. These patterns refuse a write before
# it leaves the process. Deliberately conservative — a false positive costs a
# memory, a false negative costs a credential.
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE),
    re.compile(
        r"\b(password|passwd|passphrase|api[_-]?key|secret|token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
)


def looks_like_secret(text: str) -> bool:
    """True when content matches a known credential shape (§47)."""
    return any(p.search(text or "") for p in _SECRET_PATTERNS)


class SecretRefused(Exception):
    """Content looked like a credential and was refused before any write."""


class LifeOpsUnavailable(Exception):
    """LifeOps Core could not be reached. Callers degrade, never crash."""


class LifeOpsError(Exception):
    """LifeOps answered with an HTTP error status."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def _extract_memories(payload: Any) -> list[dict[str, Any]]:
    """Tolerate the list envelopes LifeOps uses ({'memories': [...]})."""
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    if isinstance(payload, dict):
        for key in ("memories", "results", "items"):
            items = payload.get(key)
            if isinstance(items, list):
                return [m for m in items if isinstance(m, dict)]
    return []


class LifeOpsMemoryClient:
    """Synchronous client with retry/backoff. Threads are the caller's job."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        client_id: str = DEFAULT_CLIENT_ID,
        timeout: float = 2.0,
        max_retries: int = 2,
        backoff: float = 0.2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, max_retries)
        self._backoff = max(0.0, backoff)
        self._http = httpx.Client(
            timeout=timeout,
            headers={CLIENT_HEADER: client_id},
        )

    def close(self) -> None:
        self._http.close()

    # -- transport -----------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{API_PREFIX}{path}"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._http.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(self._backoff * (2**attempt))
                continue
            if resp.status_code >= 400:
                raise LifeOpsError(resp.status_code, _error_detail(resp))
            try:
                return resp.json()
            except ValueError:
                return {}
        raise LifeOpsUnavailable(f"{method} {url} failed: {last_exc}")

    # -- memory API ----------------------------------------------------------

    def store(
        self,
        content: str,
        type: str,  # noqa: A002 — mirrors the §45 field name
        source_type: str,
        source_id: str | None = None,
        confidence: float | None = None,
        importance: float | None = None,
        entity_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /memory. Raises SecretRefused before any network call."""
        if looks_like_secret(content):
            raise SecretRefused("content matches a credential pattern (BUILD_SPEC §47)")
        body: dict[str, Any] = {
            "content": content,
            "type": type,
            "source_type": source_type,
        }
        if source_id:
            body["source_id"] = source_id
        if confidence is not None:
            body["confidence"] = confidence
        if importance is not None:
            body["importance"] = importance
        if entity_ids:
            body["entity_ids"] = entity_ids
        payload = self._request("POST", "/memory", json=body)
        return payload if isinstance(payload, dict) else {}

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """GET /memory/search?q=..."""
        payload = self._request(
            "GET", "/memory/search", params={"q": query, "limit": limit}
        )
        return _extract_memories(payload)

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """GET /memory — recent memories, newest first."""
        payload = self._request("GET", "/memory", params={"limit": limit})
        return _extract_memories(payload)

    def invalidate(self, memory_id: str, reason: str) -> dict[str, Any]:
        """POST /memory/{id}/invalidate — closes validity, never deletes.

        The reason is required server-side: it becomes part of the record's
        history (§45).
        """
        payload = self._request(
            "POST", f"/memory/{memory_id}/invalidate", json={"reason": reason}
        )
        return payload if isinstance(payload, dict) else {}


def _error_detail(resp: httpx.Response) -> str:
    """Pull the stable error code/detail out of a LifeOps error body."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    if isinstance(body, dict):
        for key in ("error", "detail", "message"):
            value = body.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, dict) and isinstance(value.get("code"), str):
                return value["code"]
    return resp.text[:200]
