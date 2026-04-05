from pathlib import Path

from app.services.agent.identity import IdentityLoader


def test_identity_loader_parses_markdown_and_hot_reloads(tmp_path: Path):
    agent_dir = tmp_path / "tester"
    agent_dir.mkdir(parents=True)
    (agent_dir / "memory").mkdir()
    (agent_dir / "AGENT.md").write_text(
        """---
name: Runtime Tester
model: gpt-4o-mini
capabilities:
  - plan
  - search
constraints:
  - stay concise
---

Follow the operator request exactly.
""",
        encoding="utf-8",
    )
    (agent_dir / "SOUL.md").write_text(
        """## Personality
Focused and practical.

## Tone
Direct.

## Rules
- Prefer tools when needed.
""",
        encoding="utf-8",
    )
    (agent_dir / "MEMORY.md").write_text("Persistent fact.", encoding="utf-8")
    (agent_dir / "TOOLS.md").write_text(
        """## LLM Provider
provider: openai
model: gpt-4o-mini
temperature: 0.1

## CLI Agents Available
- codex: coding
""",
        encoding="utf-8",
    )

    loader = IdentityLoader(tmp_path)
    identity = loader.load("tester")
    assert identity.name == "Runtime Tester"
    assert identity.capabilities == ["plan", "search"]
    assert identity.rules == ["Prefer tools when needed."]
    assert identity.cli_agents[0].name == "codex"
    assert "Persistent fact." in identity.system_prompt

    (agent_dir / "MEMORY.md").write_text("Updated fact.", encoding="utf-8")
    identity2 = loader.load("tester")
    assert "Updated fact." in identity2.long_term_memory
