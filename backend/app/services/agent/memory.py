"""Memory management for runtime agents."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.database.qdrant_client import qdrant_manager
from app.services.agent.models import MemoryEntry
from app.services.embedding import embedding_service
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, agents_root, max_memory_tokens: int = 1200):
        self.agents_root = Path(agents_root)
        self.max_memory_tokens = max_memory_tokens

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation using len//4. Consider using tiktoken for accuracy."""
        if not text:
            return 0
        count = len(text) // 4
        if count > 500:
            logger.debug("Token estimation using len//4 heuristic (%d tokens for %d chars); consider tiktoken for accuracy", count, len(text))
        return max(1, count)



class MemoryManager:
    def __init__(self, agents_root: Path, max_memory_tokens: int = 1200):
        self.agents_root = Path(agents_root)
        self.max_memory_tokens = max_memory_tokens
        self._working_memory: dict[str, list[MemoryEntry]] = {}

    def _memory_dir(self, agent_id: str) -> Path:
        memory_dir = self.agents_root / agent_id / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        return memory_dir

    def load_long_term_memory(self, agent_id: str) -> str:
        path = self.agents_root / agent_id / "MEMORY.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    async def retrieve_relevant(self, agent_id: str, query: str, limit: int = 5) -> List[MemoryEntry]:
        entries: List[MemoryEntry] = []
        long_term = self.load_long_term_memory(agent_id).strip()
        if long_term:
            entries.append(
                MemoryEntry(
                    id=f"{agent_id}:memory-md",
                    content=long_term,
                    source="memory_md",
                    tokens=MemoryManager._estimate_tokens(long_term),
                )
            )

        client = qdrant_manager.get_async_client()
        try:
            embedding = await embedding_service.embed_text(query)
            results = await client.search(
                collection_name="agent_memories",
                query_vector=embedding.tolist(),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            for point in results:
                payload = dict(point.payload or {})
                if payload.get("agent_name") and payload.get("agent_name") != agent_id:
                    continue
                content = payload.get("content", "")
                entries.append(
                    MemoryEntry(
                        id=str(point.id),
                        content=content,
                        source="qdrant",
                        timestamp=payload.get("timestamp"),
                        score=point.score,
                        metadata=payload,
                        tokens=MemoryManager._estimate_tokens(content),
                    )
                )
        except Exception as exc:
            logger.warning("Memory retrieval skipped for %s: %s", agent_id, exc)

        budget = self.max_memory_tokens
        trimmed: List[MemoryEntry] = []
        for entry in entries:
            if budget - entry.tokens < 0:
                break
            trimmed.append(entry)
            budget -= entry.tokens
        return trimmed

    def add_working_memory(self, agent_id: str, content: str, *, source: str = "working") -> None:
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            content=content,
            source=source,  # type: ignore[arg-type]
            timestamp=utc_now_iso(),
            tokens=MemoryManager._estimate_tokens(content),
        )
        self._working_memory.setdefault(agent_id, []).append(entry)

    async def write_daily_log(self, agent_id: str, content: str, timestamp: Optional[str] = None) -> Path:
        timestamp = timestamp or utc_now_iso()
        day = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat()
        target = self._memory_dir(agent_id) / f"{day}.md"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"## {timestamp}\n\n{content}\n\n")
        return target

    async def flush_working_memory(self, agent_id: str) -> None:
        client = qdrant_manager.get_async_client()
        entries = self._working_memory.pop(agent_id, [])
        for entry in entries:
            await self.write_daily_log(agent_id, entry.content, entry.timestamp)
            try:
                embedding = await embedding_service.embed_text(entry.content)
                await client.upsert(
                    collection_name="agent_memories",
                    points=[{
                        "id": entry.id,
                        "vector": embedding.tolist(),
                        "payload": {
                            "id": entry.id,
                            "agent_name": agent_id,
                            "memory_type": entry.source,
                            "content": entry.content,
                            "timestamp": entry.timestamp or utc_now_iso(),
                        },
                    }],
                )
            except Exception as exc:
                logger.warning("Skipping qdrant memory flush for %s: %s", agent_id, exc)
