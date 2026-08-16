"""Per-agent usage and rate limiting."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import DefaultDict, Deque, Dict

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentIdentity, AgentUsageSnapshot
from app.utils.time import utc_now_iso

DEFAULT_REQUESTS_PER_MINUTE = 30
DEFAULT_TOKENS_PER_DAY = 200_000


@dataclass
class _MinuteWindow:
    timestamps: Deque[float]


class AgentRateLimitExceeded(Exception):
    def __init__(self, message: str, snapshot: AgentUsageSnapshot, *, retry_after_seconds: int):
        super().__init__(message)
        self.message = message
        self.snapshot = snapshot
        self.retry_after_seconds = retry_after_seconds


class AgentRateLimiter:
    def __init__(self):
        self._requests: DefaultDict[str, _MinuteWindow] = defaultdict(lambda: _MinuteWindow(deque()))
        self._lock = asyncio.Lock()

    def _minute_limit(self, identity: AgentIdentity) -> int:
        return int(identity.rate_limits.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE))

    def _day_limit(self, identity: AgentIdentity) -> int:
        return int(identity.rate_limits.get("tokens_per_day", DEFAULT_TOKENS_PER_DAY))

    def _key(self, agent_id: str, user_id: str) -> str:
        return f"{agent_id}:{user_id}"

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    async def check_request_limit(self, *, agent_id: str, user_id: str, identity: AgentIdentity) -> AgentUsageSnapshot:
        async with self._lock:
            key = self._key(agent_id, user_id)
            now = asyncio.get_running_loop().time()
            window = self._requests[key].timestamps
            while window and now - window[0] >= 60:
                window.popleft()
            minute_limit = self._minute_limit(identity)
            if len(window) >= minute_limit:
                retry_after = max(1, int(60 - (now - window[0])))
                today = self._today()
                daily = await sqlite_manager.get_agent_token_usage(agent_id, user_id, today)
                raise AgentRateLimitExceeded(
                    f"Rate limit exceeded for agent '{agent_id}'. Retry in {retry_after} seconds.",
                    AgentUsageSnapshot(
                        agent_id=agent_id,
                        user_id=user_id,
                        minute_requests=len(window),
                        minute_limit=minute_limit,
                        daily_tokens=int((daily or {}).get("total_tokens") or 0),
                        daily_token_limit=self._day_limit(identity),
                        daily_requests=int((daily or {}).get("total_requests") or 0),
                        retry_after_seconds=retry_after,
                        date=today,
                    ),
                    retry_after_seconds=retry_after,
                )
            window.append(now)

        daily = await sqlite_manager.get_agent_token_usage(agent_id, user_id, self._today())
        return AgentUsageSnapshot(
            agent_id=agent_id,
            user_id=user_id,
            minute_requests=len(self._requests[self._key(agent_id, user_id)].timestamps),
            minute_limit=self._minute_limit(identity),
            daily_tokens=int((daily or {}).get("total_tokens") or 0),
            daily_token_limit=self._day_limit(identity),
            daily_requests=int((daily or {}).get("total_requests") or 0),
            date=self._today(),
        )

    async def record_usage(
        self, *, agent_id: str, user_id: str, tokens: int, request_increment: int = 1
    ) -> AgentUsageSnapshot:
        date = self._today()
        row = await sqlite_manager.get_agent_token_usage(agent_id, user_id, date)
        total_tokens = int((row or {}).get("total_tokens") or 0) + max(tokens, 0)
        total_requests = int((row or {}).get("total_requests") or 0) + max(request_increment, 0)
        await sqlite_manager.upsert_agent_token_usage(
            {
                "id": (row or {}).get("id") or str(uuid.uuid4()),
                "agent_id": agent_id,
                "user_id": user_id,
                "date": date,
                "total_tokens": total_tokens,
                "total_requests": total_requests,
                "created_at": (row or {}).get("created_at") or utc_now_iso(),
            }
        )
        return AgentUsageSnapshot(
            agent_id=agent_id,
            user_id=user_id,
            minute_requests=len(self._requests[self._key(agent_id, user_id)].timestamps),
            minute_limit=0,
            daily_tokens=total_tokens,
            daily_token_limit=0,
            daily_requests=total_requests,
            date=date,
        )

    async def enforce_daily_token_limit(
        self, *, agent_id: str, user_id: str, identity: AgentIdentity, projected_tokens: int
    ) -> AgentUsageSnapshot:
        row = await sqlite_manager.get_agent_token_usage(agent_id, user_id, self._today())
        current_tokens = int((row or {}).get("total_tokens") or 0)
        limit = self._day_limit(identity)
        if current_tokens + projected_tokens > limit:
            raise AgentRateLimitExceeded(
                f"Daily token budget exceeded for agent '{agent_id}'.",
                AgentUsageSnapshot(
                    agent_id=agent_id,
                    user_id=user_id,
                    minute_requests=len(self._requests[self._key(agent_id, user_id)].timestamps),
                    minute_limit=self._minute_limit(identity),
                    daily_tokens=current_tokens,
                    daily_token_limit=limit,
                    daily_requests=int((row or {}).get("total_requests") or 0),
                    retry_after_seconds=86400,
                    date=self._today(),
                ),
                retry_after_seconds=86400,
            )
        return AgentUsageSnapshot(
            agent_id=agent_id,
            user_id=user_id,
            minute_requests=len(self._requests[self._key(agent_id, user_id)].timestamps),
            minute_limit=self._minute_limit(identity),
            daily_tokens=current_tokens,
            daily_token_limit=limit,
            daily_requests=int((row or {}).get("total_requests") or 0),
            date=self._today(),
        )

    async def get_usage(self, *, agent_id: str, user_id: str, identity: AgentIdentity) -> dict:
        row = await sqlite_manager.get_agent_token_usage(agent_id, user_id, self._today())
        history = await sqlite_manager.list_agent_token_usage(agent_id, user_id=user_id, limit=14)
        return {
            "current": AgentUsageSnapshot(
                agent_id=agent_id,
                user_id=user_id,
                minute_requests=len(self._requests[self._key(agent_id, user_id)].timestamps),
                minute_limit=self._minute_limit(identity),
                daily_tokens=int((row or {}).get("total_tokens") or 0),
                daily_token_limit=self._day_limit(identity),
                daily_requests=int((row or {}).get("total_requests") or 0),
                date=self._today(),
            ).model_dump(),
            "history": history,
        }


agent_rate_limiter = AgentRateLimiter()
