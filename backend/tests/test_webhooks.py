import json
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_incoming_webhook_returns_400_for_invalid_json(test_client, mock_sqlite_manager):
    client = test_client
    row = {
        "id": "hook-1",
        "agent_id": "analyst",
        "name": "Inbound",
        "url_path": "incoming-hook",
        "secret": "topsecret",
        "event_type": "build.finished",
        "enabled": True,
    }
    mock_sqlite_manager._storage["agent_webhooks"][row["id"]] = row

    body = b"{invalid"
    signature = AgentWebhookService().build_signature(row["secret"], body)

    with patch(
        "app.routers.agent_webhooks.get_agent_runtime",
        return_value=AsyncMock(handle_incoming_webhook=AsyncMock(side_effect=json.JSONDecodeError("bad json", "{invalid", 1))),
    ):
        response = await client.post(
            "/api/v1/webhooks/incoming/incoming-hook",
            content=body,
            headers={
                "X-KnowledgeOS-Signature": signature,
                "X-KnowledgeOS-Event": "build.finished",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON payload"
