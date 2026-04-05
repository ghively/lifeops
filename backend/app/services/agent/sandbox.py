"""Tool sandboxing and approval flow."""
from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.config import BASE_DIR


MAX_TOOL_OUTPUT_BYTES = 10 * 1024
SECRET_ENV_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in ["token", "secret", "password", "key"]]


class ToolApprovalRequired(Exception):
    def __init__(self, request: Dict[str, Any]):
        super().__init__("Tool approval required")
        self.request = request


class ToolApprovalManager:
    def __init__(self):
        self._pending: Dict[str, asyncio.Future[bool]] = {}
        self._payloads: Dict[str, Dict[str, Any]] = {}

    async def create_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        enriched = {**payload, "request_id": request_id, "timeout_seconds": 60}
        self._pending[request_id] = future
        self._payloads[request_id] = enriched
        return enriched

    async def wait_for_decision(self, request_id: str, timeout_seconds: int = 60) -> bool:
        future = self._pending[request_id]
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            self.resolve(request_id, approved=False)
            return False

    def resolve(self, request_id: str, approved: bool) -> None:
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(bool(approved))
        self._pending.pop(request_id, None)
        self._payloads.pop(request_id, None)

    def get_payload(self, request_id: str) -> Optional[Dict[str, Any]]:
        return self._payloads.get(request_id)


class ToolSandbox:
    def __init__(self, allowed_paths: Optional[Iterable[str]] = None):
        default_root = str(BASE_DIR.parent.resolve())
        self.allowed_paths = [Path(path).expanduser().resolve() for path in (allowed_paths or [default_root])]

    def allowed_for_identity(self, identity_preferences: Dict[str, Any] | None = None) -> "ToolSandbox":
        configured_paths = identity_preferences.get("allowed_paths") if identity_preferences else None
        if configured_paths:
            return ToolSandbox(configured_paths)
        return self

    def validate_path(self, path_value: str) -> Path:
        path = Path(path_value).expanduser().resolve()
        for allowed in self.allowed_paths:
            if path == allowed or allowed in path.parents:
                return path
        raise PermissionError(f"Path '{path}' is outside the sandbox")

    def truncate_output(self, text: str) -> tuple[str, bool]:
        raw = (text or "").encode("utf-8", errors="replace")
        if len(raw) <= MAX_TOOL_OUTPUT_BYTES:
            return text, False
        truncated = raw[:MAX_TOOL_OUTPUT_BYTES].decode("utf-8", errors="ignore")
        return truncated + "\n...[truncated]", True

    def filtered_env(self, env: Dict[str, str] | None = None) -> Dict[str, str]:
        filtered = {}
        for key, value in (env or os.environ).items():
            if any(pattern.search(key) for pattern in SECRET_ENV_PATTERNS):
                continue
            filtered[key] = value
        return filtered


tool_approval_manager = ToolApprovalManager()

