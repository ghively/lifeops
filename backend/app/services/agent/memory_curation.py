"""Background memory curation for runtime agents."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.services.agent.models import LLMProviderConfig
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


class MemoryCurationService:
    def __init__(self, agents_root: Path, identity_loader, llm_router):
        self.agents_root = Path(agents_root)
        self.identity_loader = identity_loader
        self.llm_router = llm_router

    async def curate_agent_memory(self, agent_id: str, *, frequency: str = "daily") -> Dict[str, object]:
        identity = self.identity_loader.load(agent_id)
        memory_dir = self.agents_root / agent_id / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_path = self.agents_root / agent_id / "MEMORY.md"
        daily_logs = sorted(path for path in memory_dir.glob("*.md") if self._is_daily_log(path))
        weekly_groups = self._group_logs_by_week(daily_logs)
        weekly_summaries: List[Path] = []

        for week_key, paths in weekly_groups.items():
            if len(paths) < 2:
                continue
            summary_path = memory_dir / f"{week_key}.summary.md"
            summary_text = await self._summarize_logs(identity.llm or LLMProviderConfig(), agent_id, paths, week_key)
            summary_path.write_text(summary_text, encoding="utf-8")
            weekly_summaries.append(summary_path)
            for path in paths:
                path.unlink(missing_ok=True)

        existing_memory = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
        curated_memory = await self._curate_memory_file(
            identity.llm or LLMProviderConfig(),
            agent_id,
            existing_memory,
            sorted(memory_dir.glob("*.summary.md")),
            frequency=frequency,
        )
        memory_path.write_text(curated_memory, encoding="utf-8")

        return {
            "agent_id": agent_id,
            "updated_at": utc_now_iso(),
            "weekly_summaries_created": [path.name for path in weekly_summaries],
            "memory_file": str(memory_path),
        }

    def _is_daily_log(self, path: Path) -> bool:
        try:
            datetime.strptime(path.stem, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _group_logs_by_week(self, daily_logs: List[Path]) -> Dict[str, List[Path]]:
        grouped: Dict[str, List[Path]] = defaultdict(list)
        now = datetime.now(timezone.utc).date()
        for path in daily_logs:
            day = datetime.strptime(path.stem, "%Y-%m-%d").date()
            age_days = (now - day).days
            if age_days < 7:
                continue
            year, week, _ = day.isocalendar()
            grouped[f"{year}-W{week:02d}"].append(path)
        return grouped

    async def _summarize_logs(self, config: LLMProviderConfig, agent_id: str, paths: List[Path], week_key: str) -> str:
        logs_blob = "\n\n".join(f"## {path.stem}\n{path.read_text(encoding='utf-8')}" for path in paths)
        prompt = (
            f"Summarize these daily logs for agent {agent_id} into a weekly memory summary. "
            "Keep durable facts, recurring goals, and unresolved issues. Exclude transient chatter.\n\n"
            f"Week: {week_key}\n\n{logs_blob}"
        )
        response = await self.llm_router.complete([{"role": "user", "content": prompt}], config=config)
        content = (response.get("content") or "").strip()
        return f"# Weekly Summary {week_key}\n\n{content}\n"

    async def _curate_memory_file(
        self,
        config: LLMProviderConfig,
        agent_id: str,
        existing_memory: str,
        summary_paths: List[Path],
        *,
        frequency: str,
    ) -> str:
        summary_blob = "\n\n".join(path.read_text(encoding="utf-8") for path in summary_paths[-8:])
        prompt = (
            f"Curate MEMORY.md for agent {agent_id}. Remove outdated or contradictory items, keep durable truths, "
            f"and fold in weekly summaries. This runs on a {frequency} cadence.\n\n"
            f"Current MEMORY.md:\n{existing_memory}\n\n"
            f"Weekly summaries:\n{summary_blob}\n\n"
            "Return only the revised MEMORY.md content."
        )
        response = await self.llm_router.complete([{"role": "user", "content": prompt}], config=config)
        content = (response.get("content") or "").strip()
        if content:
            return content
        logger.warning("Memory curation returned empty content for %s", agent_id)
        return existing_memory
