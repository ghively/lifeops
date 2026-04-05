import json

import pytest

import app.services.agent.webhooks as webhooks_module
from app.services.agent.webhooks import AgentWebhookService


@pytest.mark.asyncio
async def test_webhook_creation_hmac_and_triggering(mock_sqlite_manager):
    service = AgentWebhookService()
    webhooks_module.sqlite_manager = mock_sqlite_manager

    class StubRuntime:
        async def run_background_task(self, **kwargs):
            return {"content": "webhook handled", "session_id": "hook-session", "tool_results": []}

    service.bind_runtime(StubRuntime())

    webhook = await service.create_webhook(agent_id="analyst", name="Inbound", event_type="build.finished")
    assert webhook.id in mock_sqlite_manager._storage["agent_webhooks"]

    body = json.dumps({"message": "Process build event"}).encode("utf-8")
    signature = service.build_signature(webhook.secret, body)
    result = await service.verify_and_handle(
        hook_id=webhook.url_path,
        body=body,
        signature=signature,
        event_type="build.finished",
    )
    assert result["result"]["content"] == "webhook handled"

    assert service.verify_signature(webhook.secret, body, signature) is True
    assert service.verify_signature(webhook.secret, body, "sha256=bad") is False
