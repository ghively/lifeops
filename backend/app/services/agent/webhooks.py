"""Webhook registration and trigger handling for runtime agents."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from typing import Any, Dict, Optional

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentWebhook


class AgentWebhookService:
    def __init__(self):
        self.runtime = None

    def bind_runtime(self, runtime) -> None:
        self.runtime = runtime

    async def create_webhook(
        self,
        *,
        agent_id: str,
        name: str,
        event_type: str,
        enabled: bool = True,
    ) -> AgentWebhook:
        webhook = AgentWebhook(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            name=name,
            url_path=secrets.token_urlsafe(24),
            secret=secrets.token_urlsafe(32),
            event_type=event_type,
            enabled=enabled,
        )
        await sqlite_manager.create_agent_webhook(webhook.model_dump())
        return webhook

    async def list_webhooks(self, agent_id: Optional[str] = None) -> list[AgentWebhook]:
        return [AgentWebhook(**row) for row in await sqlite_manager.list_agent_webhooks(agent_id)]

    async def delete_webhook(self, webhook_id: str) -> None:
        await sqlite_manager.delete_agent_webhook(webhook_id)

    async def get_webhook(self, webhook_id: str) -> Optional[AgentWebhook]:
        row = await sqlite_manager.get_agent_webhook(webhook_id)
        return AgentWebhook(**row) if row else None

    async def verify_and_handle(
        self,
        *,
        hook_id: str,
        body: bytes,
        signature: str,
        event_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = await sqlite_manager.get_agent_webhook_by_path(hook_id)
        if not row:
            raise KeyError(f"Unknown webhook: {hook_id}")
        webhook = AgentWebhook(**row)
        if not webhook.enabled:
            raise PermissionError("Webhook is disabled")
        if event_type and webhook.event_type != event_type:
            raise ValueError("Webhook event type does not match")
        if not self.verify_signature(webhook.secret, body, signature):
            raise PermissionError("Invalid webhook signature")
        if self.runtime is None:
            raise RuntimeError("Webhook service is not bound to the runtime")
        payload = json.loads(body.decode("utf-8") or "{}")
        result = await self.runtime.run_background_task(
            agent_id=webhook.agent_id,
            message=str(payload.get("message") or f"Handle webhook event: {webhook.event_type}"),
            shared_context={
                "webhook_id": webhook.id,
                "event_type": webhook.event_type,
                "payload": payload,
            },
            timeout_seconds=int(payload.get("timeout_seconds") or 120),
            metadata={"webhook_id": webhook.id, "event_type": webhook.event_type},
        )
        return {"webhook": webhook.model_dump(), "result": result}

    def verify_signature(self, secret: str, body: bytes, signature: str) -> bool:
        expected = self.build_signature(secret, body)
        provided = signature.strip()
        return hmac.compare_digest(expected, provided)

    def build_signature(self, secret: str, body: bytes) -> str:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"
