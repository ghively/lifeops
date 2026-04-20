"""Agent identity loading from markdown files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.services.agent.models import AgentIdentity, CLIAgentConfig, LLMProviderConfig, MCPServerConfig

try:
    import yaml
except ImportError:  # pragma: no cover - dependency installed in backend runtime
    yaml = None

logger = logging.getLogger(__name__)

DEFAULT_AGENT_FILES = {
    "AGENT.md": """---
name: Default Agent
model: qwen2.5-coder:7b
capabilities:
  - chat
  - search
constraints:
  - Respect repository boundaries.
---

You are the default Knowledge OS runtime agent.
""",
    "SOUL.md": """## Personality
Pragmatic, clear, and focused.

## Tone
Direct and concise.

## Rules
- Prefer actionable answers.
- Use tools only when they materially help.
""",
    "MEMORY.md": """# Long-Term Memory

This agent is newly created. Curate durable facts here over time.
""",
    "TOOLS.md": """## LLM Provider
provider: ollama
model: qwen2.5-coder:7b
temperature: 0.2
max_tokens: 2048

## CLI Agents Available
- codex: coding, file editing, git operations
- gemini: analysis and research

## MCP Servers
mcp_servers: []
""",
}


class IdentityLoader:
    """Loads and caches agent identity markdown files."""

    def __init__(self, agents_root: Path):
        self.agents_root = Path(agents_root)
        self._cache: Dict[str, AgentIdentity] = {}

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_root / agent_id

    def ensure_agent(self, agent_id: str) -> Path:
        agent_dir = self.agent_dir(agent_id)
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "memory").mkdir(exist_ok=True)
        for filename, content in DEFAULT_AGENT_FILES.items():
            target = agent_dir / filename
            if not target.exists():
                target.write_text(content, encoding="utf-8")
        return agent_dir

    def list_agents(self) -> List[Dict[str, Any]]:
        self.agents_root.mkdir(parents=True, exist_ok=True)
        agents: List[Dict[str, Any]] = []
        for child in sorted(self.agents_root.iterdir()):
            if child.is_dir():
                agents.append({"id": child.name, "path": str(child)})
        return agents

    def delete_agent(self, agent_id: str) -> None:
        agent_dir = self.agent_dir(agent_id)
        if not agent_dir.exists():
            return
        for path in sorted(agent_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        agent_dir.rmdir()
        self._cache.pop(agent_id, None)

    def get_file(self, agent_id: str, name: str) -> str:
        return (self.ensure_agent(agent_id) / name).read_text(encoding="utf-8")

    def update_file(self, agent_id: str, name: str, content: str) -> None:
        (self.ensure_agent(agent_id) / name).write_text(content, encoding="utf-8")
        self._cache.pop(agent_id, None)

    def load(self, agent_id: str, *, create_if_missing: bool = False) -> AgentIdentity:
        agent_dir = self.agent_dir(agent_id)
        if not agent_dir.exists():
            if not create_if_missing:
                raise FileNotFoundError(f"Agent '{agent_id}' does not exist at {agent_dir}")
            agent_dir = self.ensure_agent(agent_id)
        file_mtimes = self._file_mtimes(agent_dir)
        cached = self._cache.get(agent_id)
        if cached and cached.file_mtimes == file_mtimes:
            return cached

        agent_meta, agent_body = self._parse_frontmatter_file(agent_dir / "AGENT.md")
        soul_meta, soul_body = self._parse_frontmatter_file(agent_dir / "SOUL.md")
        memory_meta, memory_body = self._parse_frontmatter_file(agent_dir / "MEMORY.md")
        tools_meta, tools_body = self._parse_frontmatter_file(agent_dir / "TOOLS.md")

        soul_sections = self._parse_sections(soul_body)
        tool_sections = self._parse_sections(tools_body)

        identity = AgentIdentity(
            agent_id=agent_id,
            name=str(agent_meta.get("name") or agent_id),
            model=str(agent_meta.get("model") or tools_meta.get("model")),
            capabilities=self._coerce_list(agent_meta.get("capabilities")),
            constraints=self._coerce_list(agent_meta.get("constraints")),
            instructions=agent_body.strip(),
            personality=(soul_meta.get("personality") or soul_sections.get("personality") or "").strip(),
            tone=(soul_meta.get("tone") or soul_sections.get("tone") or "").strip(),
            rules=self._coerce_list(soul_meta.get("rules")) or self._parse_bullets(soul_sections.get("rules", "")),
            long_term_memory=(memory_meta.get("memory") or memory_body).strip(),
            llm=self._build_llm_config(tools_meta, tool_sections, agent_meta),
            cli_agents=self._build_cli_agents(tool_sections),
            mcp_servers=self._build_mcp_servers(tool_sections),
            tool_preferences={"tools_md": tools_body.strip(), **self._build_tool_preferences(tool_sections, tools_meta)},
            rate_limits=self._build_rate_limits(agent_meta, tools_meta, tool_sections),
            file_mtimes=file_mtimes,
        )
        identity.system_prompt = self._build_system_prompt(identity)
        self._cache[agent_id] = identity
        return identity

    def _file_mtimes(self, agent_dir: Path) -> Dict[str, float]:
        mtimes: Dict[str, float] = {}
        for name in DEFAULT_AGENT_FILES:
            path = agent_dir / name
            mtimes[name] = float(path.stat().st_mtime_ns) if path.exists() else 0.0
        return mtimes

    def _parse_frontmatter_file(self, path: Path) -> Tuple[Dict[str, Any], str]:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if not text.startswith("---\n"):
            return {}, text
        parts = text.split("\n---\n", 1)
        if len(parts) != 2:
            return {}, text
        return self._parse_frontmatter(parts[0][4:]), parts[1]

    def _parse_frontmatter(self, text: str) -> Dict[str, Any]:
        if yaml is not None:
            try:
                parsed = yaml.safe_load(text) or {}
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                logger.debug("YAML frontmatter parse failed, falling back to line parser", exc_info=True)
        data: Dict[str, Any] = {}
        current_key: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            if line.lstrip().startswith("- ") and current_key:
                data.setdefault(current_key, []).append(self._parse_scalar(line.split("- ", 1)[1].strip()))
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if not value:
                data[current_key] = []
            else:
                data[current_key] = self._parse_scalar(value)
        return data

    def _parse_scalar(self, value: str) -> Any:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered.isdigit():
            return int(lowered)
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [item.strip().strip("'\"") for item in inner.split(",")]
        return value.strip().strip("'\"")

    def _parse_sections(self, text: str) -> Dict[str, str]:
        sections: Dict[str, List[str]] = {}
        current = "body"
        sections[current] = []
        for line in text.splitlines():
            if line.startswith("## "):
                current = line[3:].strip().lower()
                sections.setdefault(current, [])
                continue
            sections.setdefault(current, []).append(line)
        return {key: "\n".join(value).strip() for key, value in sections.items()}

    def _parse_bullets(self, text: str) -> List[str]:
        return [line.split("- ", 1)[1].strip() for line in text.splitlines() if line.strip().startswith("- ")]

    def _coerce_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [part.strip() for part in stripped.split(",")]
        return [str(value)]

    def _build_llm_config(
        self,
        tools_meta: Dict[str, Any],
        tool_sections: Dict[str, str],
        agent_meta: Dict[str, Any],
    ) -> LLMProviderConfig:
        provider_blob = tool_sections.get("llm provider", "")
        parsed = self._parse_frontmatter(provider_blob.replace("\n", "\n"))
        from app.config import settings

        model = (
            tools_meta.get("model")
            or parsed.get("model")
            or agent_meta.get("model")
            or getattr(settings, "llm_model", "qwen2.5-coder:7b")
        )
        return LLMProviderConfig(
            provider=str(tools_meta.get("provider") or parsed.get("provider") or getattr(settings, "llm_provider", "ollama")),
            base_url=tools_meta.get("base_url") or parsed.get("base_url"),
            api_key=tools_meta.get("api_key") or parsed.get("api_key"),
            model=str(model),
            temperature=float(
                tools_meta.get("temperature") or parsed.get("temperature") or getattr(settings, "llm_temperature", 0.2)
            ),
            max_tokens=int(
                tools_meta.get("max_tokens") or parsed.get("max_tokens") or getattr(settings, "llm_max_tokens", 2048)
            ),
            fallback_model=tools_meta.get("fallback") or parsed.get("fallback"),
        )

    def _build_cli_agents(self, tool_sections: Dict[str, str]) -> List[CLIAgentConfig]:
        cli_section = tool_sections.get("cli agents available", "")
        configs: List[CLIAgentConfig] = []
        for item in self._parse_bullets(cli_section):
            name, _, description = item.partition(":")
            clean_name = name.strip()
            if not clean_name:
                continue
            configs.append(CLIAgentConfig(name=clean_name, command=clean_name, description=description.strip()))
        return configs

    def _build_mcp_servers(self, tool_sections: Dict[str, str]) -> List[Dict[str, Any]]:
        mcp_section = tool_sections.get("mcp servers", "")
        if not mcp_section.strip():
            return []

        parsed: Any = None
        if yaml is not None:
            try:
                parsed = yaml.safe_load(mcp_section)
            except Exception:
                logger.warning("Failed to parse MCP server config from TOOLS.md", exc_info=True)

        if isinstance(parsed, dict) and isinstance(parsed.get("mcp_servers"), list):
            configs: List[Dict[str, Any]] = []
            for item in parsed["mcp_servers"]:
                if not isinstance(item, dict):
                    continue
                try:
                    configs.append(MCPServerConfig(**item).model_dump())
                except Exception:
                    logger.warning("Skipping invalid MCP server config in TOOLS.md: %s", item, exc_info=True)
            return configs

        servers: List[Dict[str, Any]] = []
        for item in self._parse_bullets(mcp_section):
            name, _, description = item.partition(":")
            clean_name = name.strip()
            if not clean_name:
                continue
            servers.append(
                MCPServerConfig(
                    name=clean_name,
                    transport="stdio",
                    command=clean_name,
                    auto_connect=False,
                    enabled=True,
                ).model_dump()
                | {"description": description.strip()}
            )
        return servers

    def _build_tool_preferences(self, tool_sections: Dict[str, str], tools_meta: Dict[str, Any]) -> Dict[str, Any]:
        preferences: Dict[str, Any] = {}
        sandbox_blob = tool_sections.get("sandbox", "")
        if sandbox_blob and yaml is not None:
            try:
                parsed = yaml.safe_load(sandbox_blob) or {}
                if isinstance(parsed, dict):
                    preferences.update(parsed)
            except Exception:
                logger.warning("Failed to parse sandbox config from TOOLS.md", exc_info=True)
        if isinstance(tools_meta.get("allowed_paths"), list):
            preferences["allowed_paths"] = tools_meta["allowed_paths"]
        if isinstance(tools_meta.get("require_tool_approval"), bool):
            preferences["require_tool_approval"] = tools_meta["require_tool_approval"]
        return preferences

    def _build_rate_limits(
        self,
        agent_meta: Dict[str, Any],
        tools_meta: Dict[str, Any],
        tool_sections: Dict[str, str],
    ) -> Dict[str, int]:
        limits: Dict[str, Any] = {}
        for source in (agent_meta.get("rate_limits"), tools_meta.get("rate_limits")):
            if isinstance(source, dict):
                limits.update(source)
        rate_blob = tool_sections.get("rate limits", "")
        if rate_blob and yaml is not None:
            try:
                parsed = yaml.safe_load(rate_blob) or {}
                if isinstance(parsed, dict):
                    limits.update(parsed)
            except Exception:
                logger.warning("Failed to parse rate limit config from TOOLS.md", exc_info=True)
        normalized: Dict[str, int] = {}
        for key, value in limits.items():
            try:
                normalized[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return normalized

    def _build_system_prompt(self, identity: AgentIdentity) -> str:
        parts = [
            f"You are {identity.name}.",
            f"Model preference: {identity.model}.",
        ]
        if identity.capabilities:
            parts.append("Capabilities:\n- " + "\n- ".join(identity.capabilities))
        if identity.constraints:
            parts.append("Constraints:\n- " + "\n- ".join(identity.constraints))
        if identity.instructions:
            parts.append("Instructions:\n" + identity.instructions)
        if identity.personality:
            parts.append("Personality:\n" + identity.personality)
        if identity.tone:
            parts.append("Tone:\n" + identity.tone)
        if identity.rules:
            parts.append("Rules:\n- " + "\n- ".join(identity.rules))
        if identity.long_term_memory:
            parts.append("Long-term memory:\n" + identity.long_term_memory)
        if identity.cli_agents:
            parts.append(
                "CLI agents:\n- "
                + "\n- ".join(f"{agent.name}: {agent.description or 'available'}" for agent in identity.cli_agents)
            )
        return "\n\n".join(part for part in parts if part.strip())
