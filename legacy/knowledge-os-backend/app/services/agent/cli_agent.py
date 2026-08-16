"""CLI agent delegation tools."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Dict, Optional

from app.services.agent.models import CLIAgentConfig, ToolResult

logger = logging.getLogger(__name__)


class CLIAgentTool:
    """Executes external CLI agents as subprocesses."""

    AGENTS: Dict[str, CLIAgentConfig] = {
        "codex": CLIAgentConfig(
            name="codex",
            command="codex",
            args=["--full-auto", "--print"],
            install_check="codex",
            timeout=300,
            description="OpenAI Codex CLI",
        ),
        "claude_code": CLIAgentConfig(
            name="claude_code",
            command="claude",
            args=["--print", "--permission-mode", "bypassPermissions"],
            install_check="claude",
            timeout=300,
            description="Claude Code CLI",
        ),
        "kimi": CLIAgentConfig(
            name="kimi",
            command="kimi",
            args=["--print"],
            install_check="kimi",
            timeout=300,
            description="Kimi CLI",
        ),
        "gemini": CLIAgentConfig(
            name="gemini",
            command="gemini",
            args=["-p"],
            install_check="gemini",
            timeout=120,
            description="Gemini CLI",
        ),
        "opencode": CLIAgentConfig(
            name="opencode",
            command="opencode",
            args=["--non-interactive"],
            install_check="opencode",
            timeout=300,
            description="OpenCode CLI",
        ),
    }

    def __init__(self, max_output_chars: int = 12000):
        self.max_output_chars = max_output_chars

    def get_config(self, agent_name: str) -> CLIAgentConfig:
        if agent_name not in self.AGENTS:
            raise KeyError(f"Unknown CLI agent: {agent_name}")
        return self.AGENTS[agent_name]

    def is_installed(self, agent_name: str) -> bool:
        config = self.get_config(agent_name)
        target = config.install_check or config.command
        return shutil.which(target) is not None

    def health_check(self) -> Dict[str, Dict[str, object]]:
        return {
            name: {
                "installed": self.is_installed(name),
                "command": config.command,
                "description": config.description,
                "timeout": config.timeout,
            }
            for name, config in self.AGENTS.items()
        }

    async def execute(
        self,
        agent_name: str,
        prompt: str,
        *,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        config = self.get_config(agent_name)
        started = time.perf_counter()

        if not self.is_installed(agent_name):
            return ToolResult(
                tool_name=agent_name,
                success=False,
                error=f"{agent_name} is not installed",
                content="",
            )

        command = [config.command, *config.args, prompt]
        logger.info("Executing CLI agent %s", agent_name)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd or str(Path.cwd()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout or config.timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return ToolResult(
                tool_name=agent_name,
                success=False,
                error=f"{agent_name} timed out",
                content="",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        content = (stdout or b"").decode("utf-8", errors="replace").strip()
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        combined = content if content else err
        truncated = False
        if len(combined) > self.max_output_chars:
            combined = combined[: self.max_output_chars] + "\n...[truncated]"
            truncated = True

        return ToolResult(
            tool_name=agent_name,
            success=process.returncode == 0,
            content=combined,
            error=err if process.returncode != 0 and err else None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            truncated=truncated,
            data={"returncode": process.returncode},
        )
