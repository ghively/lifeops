"""LifeOps memory provider for Hermes Agent (BUILD_SPEC §42–§47, §91).

A thin MemoryProvider plugin: Hermes talks to this, this talks to the LifeOps
HTTP memory API, LifeOps owns the memory in NornicDB. The plugin keeps no
memory of its own — §43 forbids a second memory database or domain model.

Safety posture (§44): this plugin can only ever create observations, episodic
memories, semantic associations, and conversational summaries through the
LifeOps memory API. There is no code path here that approves actions,
consumes approvals, touches payments or idempotency, or grants authority.

Interface reference (cited in README.md):
- https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin
- Reference implementation: plugins/memory/honcho/ in NousResearch/hermes-agent
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

try:  # Hermes runtime
    from agent.memory_provider import MemoryProvider
except ImportError:  # unit tests run without Hermes installed

    class MemoryProvider:  # type: ignore[no-redef]
        """Duck-typed stand-in for the Hermes ABC (agent/memory_provider.py)."""


try:
    from agent.memory_provider import is_trivial_prompt
except ImportError:

    def is_trivial_prompt(text: str) -> bool:  # type: ignore[misc]
        """Local fallback: greetings/acknowledgements carry no memory signal."""
        return bool(
            re.match(
                r"^\s*(hi|hello|hey|thanks|thank you|thx|ok|okay|yes|no|yep"
                r"|nope|sure|bye|good\s(morning|afternoon|evening|night))"
                r"[\s!.]*$",
                text or "",
                re.IGNORECASE,
            )
        )


from .client import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_ID,
    LifeOpsError,
    LifeOpsMemoryClient,
    LifeOpsUnavailable,
    SecretRefused,
    looks_like_secret,
)
from .schemas import TOOL_SCHEMAS  # noqa: E402

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "lifeops-memory.json"

# Gateway-internal notifications arrive through the user channel but are
# execution metadata, not conversation — they must never become durable
# memory. Anchored list, same rationale as the Honcho provider.
_INTERNAL_GATEWAY_TURN_RE = re.compile(
    r"^\s*(?:"
    r"\[ASYNC (?:DELEGATION )?(?:BATCH )?COMPLETE\[[^\]]*\]\]|"
    r"\[CONTEXT COMPACTION\[[^\]]*\]\]|"
    r"\[CONTEXT SUMMARY\]:?|"
    r"\[PRIOR CONTEXT\[[^\]]*\]\]|"
    r"\[Your active task list was preserved across context compression\]"
    r")",
    re.IGNORECASE,
)

_MAX_TURN_CHARS = 4000
_MAX_SUMMARY_CHARS = 2000
_MAX_CONTEXT_CHARS = 2000


class LifeOpsMemoryProvider(MemoryProvider):
    """Nornic-backed Hermes memory via the LifeOps HTTP memory API."""

    def __init__(self) -> None:
        self._client: LifeOpsMemoryClient | None = None
        self._session_id = ""
        self._hermes_home = ""
        self._lock = threading.Lock()
        self._prefetch_result: str | None = None  # None = nothing pending
        self._prefetch_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._mirror_thread: threading.Thread | None = None

    # -- lifecycle -----------------------------------------------------------

    @property
    def name(self) -> str:
        return "lifeops"

    def is_available(self) -> bool:
        """Local-first: always activatable. Calls degrade if LifeOps is down."""
        return True

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "base_url",
                "description": "LifeOps Core API base URL",
                "default": DEFAULT_BASE_URL,
            },
            {
                "key": "client_id",
                "description": (
                    "LifeOps client identity (decides capabilities). "
                    "Keep 'hermes-personal' for the primary assistant."
                ),
                "default": DEFAULT_CLIENT_ID,
            },
        ]

    def save_config(self, values: dict, hermes_home: str) -> None:
        """Write non-secret config to $HERMES_HOME/lifeops-memory.json."""
        path = Path(hermes_home) / CONFIG_FILENAME
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                existing = {}
        existing.update(values)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        os.chmod(path, 0o600)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Called once at agent startup. Never blocks on the network."""
        self._hermes_home = kwargs.get("hermes_home") or os.environ.get(
            "HERMES_HOME", ""
        )
        self._session_id = session_id or ""
        cfg = self._load_config()
        self._client = LifeOpsMemoryClient(**cfg)
        logger.debug(
            "LifeOps memory provider initialised (base_url=%s, client=%s)",
            cfg["base_url"],
            cfg["client_id"],
        )

    def _load_config(self) -> dict[str, Any]:
        """Resolution order: environment > $HERMES_HOME/lifeops-memory.json > defaults."""
        file_cfg: dict[str, Any] = {}
        if self._hermes_home:
            path = Path(self._hermes_home) / CONFIG_FILENAME
            if path.exists():
                try:
                    file_cfg = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError) as exc:
                    logger.warning("LifeOps memory config unreadable: %s", exc)
        timeout_raw = (
            os.environ.get("LIFEOPS_MEMORY_TIMEOUT")
            or file_cfg.get("timeout_seconds")
            or 2.0
        )
        try:
            timeout = float(timeout_raw)
        except (TypeError, ValueError):
            timeout = 2.0
        return {
            "base_url": os.environ.get("LIFEOPS_API_URL")
            or file_cfg.get("base_url")
            or DEFAULT_BASE_URL,
            "client_id": os.environ.get("LIFEOPS_CLIENT_ID")
            or file_cfg.get("client_id")
            or DEFAULT_CLIENT_ID,
            "timeout": timeout,
        }

    def system_prompt_block(self) -> str:
        return (
            "# LifeOps Memory\n"
            "Active. Relevant memories are auto-injected before turns, and "
            "memory tools are available: lifeops_search to recall specific "
            "past facts, lifeops_recent to see what was stored lately, "
            "lifeops_remember to save durable preferences and facts, "
            "lifeops_forget to invalidate a memory that is wrong. Memory "
            "records observations only — it cannot approve actions or change "
            "transactional state."
        )

    def shutdown(self) -> None:
        for thread in (self._prefetch_thread, self._sync_thread, self._mirror_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        if self._client is not None:
            self._client.close()
            self._client = None

    # -- recall (prefetch) ---------------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return recalled context for this turn, or "" when there is none.

        Consumes any result already fetched in the background by
        queue_prefetch; otherwise does one short-timeout search. Any failure
        degrades to "" — Hermes must never stall because LifeOps is down.
        """
        if not self._client or not query or not query.strip():
            return ""
        pending = self._consume_pending()
        if pending is not None:
            return pending
        return self._recall(query)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Pre-warm the next turn's recall in a daemon thread."""
        if not self._client or not query or not query.strip():
            return
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return

        def _run() -> None:
            result = self._recall(query)
            with self._lock:
                self._prefetch_result = result

        self._prefetch_thread = threading.Thread(
            target=_run, daemon=True, name="lifeops-prefetch"
        )
        self._prefetch_thread.start()

    def _consume_pending(self) -> str | None:
        with self._lock:
            result = self._prefetch_result
            self._prefetch_result = None
        return result

    def _recall(self, query: str) -> str:
        assert self._client is not None
        try:
            memories = self._client.search(query, limit=5)
        except LifeOpsUnavailable as exc:
            logger.debug("LifeOps recall skipped (unreachable): %s", exc)
            return ""
        except LifeOpsError as exc:
            logger.debug("LifeOps recall failed: %s", exc)
            return ""
        except Exception as exc:  # degrade, never crash the agent
            logger.warning("LifeOps recall unexpected error: %s", exc)
            return ""
        return _format_context(memories)

    # -- write (sync / mirror / extraction) ----------------------------------

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list | None = None,
    ) -> None:
        """Persist the completed turn as an episodic memory. Non-blocking."""
        if not self._client:
            return
        user = (user_content or "").strip()
        assistant = (assistant_content or "").strip()
        if not user and not assistant:
            return
        if _INTERNAL_GATEWAY_TURN_RE.match(user):
            return
        if is_trivial_prompt(user) and len(assistant) < 200:
            return
        content = f"User: {user}\nAssistant: {assistant}"[:_MAX_TURN_CHARS]
        if looks_like_secret(content):
            logger.info("LifeOps sync_turn skipped: content looks like a secret")
            return
        sid = session_id or self._session_id

        def _sync() -> None:
            try:
                assert self._client is not None
                self._client.store(
                    content=content,
                    type="episodic",
                    source_type="conversation",
                    source_id=sid,
                )
            except Exception as exc:
                logger.warning("LifeOps turn sync failed: %s", exc)

        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        self._sync_thread = threading.Thread(
            target=_sync, daemon=True, name="lifeops-sync-turn"
        )
        self._sync_thread.start()

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """Mirror built-in MEMORY.md / USER.md writes into LifeOps (§42)."""
        if not self._client:
            return
        if action not in {"write", "update", "append"}:
            return
        text = (content or "").strip()
        if not text or looks_like_secret(text):
            return

        def _mirror() -> None:
            try:
                assert self._client is not None
                self._client.store(
                    content=f"[{target}] {text}"[:_MAX_TURN_CHARS],
                    type="semantic",
                    source_type="agent",
                    source_id=target,
                )
            except Exception as exc:
                logger.warning("LifeOps memory mirror failed: %s", exc)

        self._mirror_thread = threading.Thread(
            target=_mirror, daemon=True, name="lifeops-mirror"
        )
        self._mirror_thread.start()

    def on_session_end(self, messages: list) -> None:
        """Session-end extraction: store one conversational summary (§43)."""
        if not self._client:
            return
        summary = _summarize_session(messages)
        if not summary or looks_like_secret(summary):
            return
        try:
            self._client.store(
                content=summary,
                type="summary",
                source_type="conversation",
                source_id=self._session_id,
            )
        except Exception as exc:
            logger.warning("LifeOps session summary failed: %s", exc)

    # -- tools ----------------------------------------------------------------

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        """Route a tool call to the memory API. Always returns a JSON string."""
        handlers = {
            "lifeops_remember": self._tool_remember,
            "lifeops_search": self._tool_search,
            "lifeops_recent": self._tool_recent,
            "lifeops_forget": self._tool_forget,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return json.dumps({"ok": False, "error": "unknown_tool"})
        if self._client is None:
            return json.dumps({"ok": False, "error": "lifeops_unavailable"})
        try:
            return json.dumps(handler(args or {}))
        except SecretRefused:
            return json.dumps(
                {
                    "ok": False,
                    "error": "secret_refused",
                    "detail": "Memory never stores credentials (BUILD_SPEC §47).",
                }
            )
        except LifeOpsUnavailable:
            return json.dumps(
                {
                    "ok": False,
                    "error": "lifeops_unavailable",
                    "detail": "LifeOps Core is unreachable; memory is paused, nothing was stored.",
                }
            )
        except LifeOpsError as exc:
            return json.dumps(
                {"ok": False, "error": "lifeops_error", "status": exc.status, "detail": exc.detail}
            )
        except ValueError as exc:
            return json.dumps({"ok": False, "error": "invalid_arguments", "detail": str(exc)})
        except Exception as exc:
            logger.warning("LifeOps tool %s failed unexpectedly: %s", tool_name, exc)
            return json.dumps({"ok": False, "error": "plugin_error"})

    def _tool_remember(self, args: dict) -> dict:
        content = (args.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        memory_type = args.get("type") or "semantic"
        source_type = args.get("source_type") or "conversation"
        memory = self._client.store(  # type: ignore[union-attr]
            content=content,
            type=memory_type,
            source_type=source_type,
            source_id=self._session_id,
        )
        return {"ok": True, "memory": memory}

    def _tool_search(self, args: dict) -> dict:
        query = (args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = _clamp(args.get("limit"), 5, 1, 25)
        memories = self._client.search(query, limit=limit)  # type: ignore[union-attr]
        return {"ok": True, "memories": memories, "total": len(memories)}

    def _tool_recent(self, args: dict) -> dict:
        limit = _clamp(args.get("limit"), 10, 1, 50)
        memories = self._client.list_recent(limit=limit)  # type: ignore[union-attr]
        return {"ok": True, "memories": memories, "total": len(memories)}

    def _tool_forget(self, args: dict) -> dict:
        memory_id = (args.get("memory_id") or "").strip()
        if not memory_id:
            raise ValueError("memory_id is required")
        reason = (args.get("reason") or "").strip()
        if not reason:
            raise ValueError("reason is required — it becomes part of the record's history")
        memory = self._client.invalidate(memory_id, reason=reason)  # type: ignore[union-attr]
        return {"ok": True, "memory": memory}


def register(ctx: Any) -> None:
    """Called by Hermes's memory plugin discovery system."""
    ctx.register_memory_provider(LifeOpsMemoryProvider())


# -- helpers ------------------------------------------------------------------


def _clamp(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def _format_context(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["## LifeOps memory (recalled)"]
    for m in memories:
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        mtype = m.get("type", "memory")
        source = m.get("source_type", "unknown")
        lines.append(f"- [{mtype}] {content} (source: {source})")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)[:_MAX_CONTEXT_CHARS]


def _summarize_session(messages: list) -> str:
    """Compact extractive digest: user/assistant text turns, truncated.

    Deliberately thin — richer extraction belongs to LifeOps (it has the LLM
    and the domain model), not to this adapter (§43).
    """
    if not isinstance(messages, list):
        return ""
    turns: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        text = content.strip()
        if role == "user" and _INTERNAL_GATEWAY_TURN_RE.match(text):
            continue
        turns.append(f"{'User' if role == 'user' else 'Assistant'}: {text[:300]}")
    if len(turns) < 2:
        return ""
    digest = "Session summary:\n" + "\n".join(turns)
    return digest[:_MAX_SUMMARY_CHARS]
