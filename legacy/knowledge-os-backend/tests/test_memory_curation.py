import pytest

from app.services.agent.identity import IdentityLoader
from app.services.agent.memory_curation import MemoryCurationService


class FakeLLMRouter:
    async def complete(self, messages, config=None):
        content = messages[0]["content"]
        if "weekly memory summary" in content:
            return {"content": "- Durable fact\n- Open issue"}
        return {"content": "# Long-Term Memory\n\n- Keep durable fact\n- Remove contradictions"}


@pytest.mark.asyncio
async def test_memory_curation_compresses_logs_and_updates_memory(tmp_path):
    loader = IdentityLoader(tmp_path)
    loader.ensure_agent("curator")
    memory_dir = tmp_path / "curator" / "memory"
    (memory_dir / "2026-03-20.md").write_text("Worked on parser fixes", encoding="utf-8")
    (memory_dir / "2026-03-21.md").write_text("Validated API changes", encoding="utf-8")
    (tmp_path / "curator" / "MEMORY.md").write_text("# Long-Term Memory\n\n- stale note", encoding="utf-8")

    service = MemoryCurationService(tmp_path, loader, FakeLLMRouter())
    result = await service.curate_agent_memory("curator")

    assert result["weekly_summaries_created"]
    summaries = sorted(memory_dir.glob("*.summary.md"))
    assert summaries
    assert "Durable fact" in summaries[0].read_text(encoding="utf-8")
    assert "Keep durable fact" in (tmp_path / "curator" / "MEMORY.md").read_text(encoding="utf-8")
