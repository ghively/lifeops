"""Multi-agent collaboration helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.agent.identity import IdentityLoader
from app.services.agent.models import AgentMention

MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9][a-zA-Z0-9._-]*)")


class AgentCollaborationService:
    def __init__(self, identity_loader: IdentityLoader):
        self.identity_loader = identity_loader
        self.runtime = None

    def bind_runtime(self, runtime) -> None:
        self.runtime = runtime

    def extract_mentions(self, *messages: str) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for message in messages:
            if not message:
                continue
            for match in MENTION_PATTERN.findall(message):
                agent_id = match.strip()
                if not agent_id or agent_id in seen:
                    continue
                if self.identity_loader.agent_dir(agent_id).exists():
                    seen.add(agent_id)
                    ordered.append(agent_id)
        return ordered

    def resolve_mentions(self, *messages: str) -> List[AgentMention]:
        mentions: List[AgentMention] = []
        for agent_id in self.extract_mentions(*messages):
            identity = self.identity_loader.load(agent_id)
            summary_parts = [identity.instructions.strip(), identity.personality.strip(), identity.tone.strip()]
            summary = " ".join(part for part in summary_parts if part)[:600]
            mentions.append(
                AgentMention(
                    agent_id=agent_id,
                    name=identity.name,
                    summary=summary,
                    system_prompt=identity.system_prompt,
                )
            )
        return mentions

    def build_context_block(self, *messages: str, shared_context: Optional[Dict[str, Any]] = None) -> str:
        blocks: List[str] = []
        mentions = self.resolve_mentions(*messages)
        if mentions:
            mention_lines = []
            for mention in mentions:
                mention_lines.append(f"@{mention.agent_id} ({mention.name}): {mention.summary}")
            blocks.append("Referenced agents:\n" + "\n".join(mention_lines))
        if shared_context:
            pairs = [f"{key}: {value}" for key, value in shared_context.items()]
            blocks.append("Shared context:\n" + "\n".join(pairs))
        return "\n\n".join(blocks).strip()

    async def route_message(
        self,
        *,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
        shared_context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout_seconds: int = 90,
    ) -> Dict[str, Any]:
        if self.runtime is None:
            raise RuntimeError("Collaboration service is not bound to the runtime")

        routed_context = dict(shared_context or {})
        routed_context.setdefault("from_agent_id", from_agent_id)
        response = await self.runtime.run_background_task(
            agent_id=to_agent_id,
            message=message,
            session_id=session_id,
            shared_context=routed_context,
            timeout_seconds=timeout_seconds,
            metadata={"routed_from_agent_id": from_agent_id, "collaboration": True},
        )
        return {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "message": message,
            "shared_context": routed_context,
            "response": response["content"],
            "session_id": response["session_id"],
            "tool_results": response["tool_results"],
        }
