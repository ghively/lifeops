import pytest

from app.services.agent.collaboration import AgentCollaborationService
from app.services.agent.identity import IdentityLoader


@pytest.mark.asyncio
async def test_agent_mention_resolution_and_context_sharing(tmp_path):
    loader = IdentityLoader(tmp_path)
    loader.ensure_agent("agentA")
    loader.ensure_agent("agentB")
    loader.update_file("agentB", "AGENT.md", "---\nname: Agent B\n---\nAgent B solves backend work.\n")
    loader.update_file("agentB", "SOUL.md", "## Personality\nDeliberate\n")

    service = AgentCollaborationService(loader)

    mentions = service.resolve_mentions("Ask @agentB to review the query plan.")
    assert len(mentions) == 1
    assert mentions[0].agent_id == "agentB"

    context = service.build_context_block("Route to @agentB", shared_context={"task": "Review API"})
    assert "@agentB" in context
    assert "task: Review API" in context


@pytest.mark.asyncio
async def test_agent_to_agent_message_routing(tmp_path):
    loader = IdentityLoader(tmp_path)
    loader.ensure_agent("parent")
    loader.ensure_agent("worker")
    service = AgentCollaborationService(loader)

    class StubRuntime:
        async def run_background_task(self, **kwargs):
            assert kwargs["agent_id"] == "worker"
            assert kwargs["shared_context"]["from_agent_id"] == "parent"
            return {"content": "Worker reply", "session_id": "sub-session", "tool_results": []}

    service.bind_runtime(StubRuntime())
    result = await service.route_message(from_agent_id="parent", to_agent_id="worker", message="Handle this")
    assert result["response"] == "Worker reply"
    assert result["session_id"] == "sub-session"
