"""Autonomous background task scheduler for runtime agents."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import schedule

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentScheduledTask, ScheduledTaskType
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTaskState:
    task: AgentScheduledTask
    job: schedule.Job | None = None


class AgentScheduler:
    def __init__(self):
        self.runtime = None
        self.memory_curation = None
        self._states: Dict[str, ScheduledTaskState] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._running_jobs: Dict[str, asyncio.Task] = {}

    def bind_runtime(self, runtime, memory_curation) -> None:
        self.runtime = runtime
        self.memory_curation = memory_curation

    async def start(self) -> None:
        await self.reload()
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
        self._loop_task = None
        for task in list(self._running_jobs.values()):
            task.cancel()
        self._running_jobs.clear()
        self._states.clear()
        schedule.clear("agent-runtime")

    async def reload(self) -> None:
        self._states.clear()
        schedule.clear("agent-runtime")
        for payload in await sqlite_manager.list_agent_scheduled_tasks():
            task = AgentScheduledTask(**payload)
            self._register_task(task)

    async def create_task(
        self,
        *,
        agent_id: str,
        name: str,
        cron_expression: str,
        task_type: ScheduledTaskType,
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> AgentScheduledTask:
        task = AgentScheduledTask(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            name=name,
            cron_expression=cron_expression,
            task_type=task_type,
            config=config or {},
            enabled=enabled,
            next_run=self._compute_next_run(cron_expression),
            created_at=utc_now_iso(),
        )
        await sqlite_manager.create_agent_scheduled_task(task.model_dump())
        self._register_task(task)
        return task

    async def list_tasks(self, agent_id: Optional[str] = None) -> list[AgentScheduledTask]:
        return [AgentScheduledTask(**row) for row in await sqlite_manager.list_agent_scheduled_tasks(agent_id)]

    async def delete_task(self, task_id: str) -> None:
        await sqlite_manager.delete_agent_scheduled_task(task_id)
        schedule.clear(task_id)
        self._states.pop(task_id, None)

    async def trigger_task(self, task_id: str) -> Dict[str, Any]:
        row = await sqlite_manager.get_agent_scheduled_task(task_id)
        if not row:
            raise KeyError(f"Unknown scheduled task: {task_id}")
        task = AgentScheduledTask(**row)
        return await self._execute_task(task)

    async def _poll_loop(self) -> None:
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)

    def _register_task(self, task: AgentScheduledTask) -> None:
        state = ScheduledTaskState(task=task)
        self._states[task.id] = state
        if not task.enabled:
            return
        state.job = self._build_schedule_job(task)

    def _build_schedule_job(self, task: AgentScheduledTask) -> schedule.Job | None:
        expression = task.cron_expression.strip()
        lower = expression.lower()
        if lower.startswith("every "):
            parts = lower.split()
            if len(parts) != 3 or not parts[1].isdigit():
                raise ValueError(f"Unsupported schedule format: {expression}")
            count = int(parts[1])
            unit = parts[2]
            builder = schedule.every(count)
            if unit.startswith("minute"):
                return builder.minutes.do(self._enqueue_job, task.id).tag("agent-runtime", task.id)
            if unit.startswith("hour"):
                return builder.hours.do(self._enqueue_job, task.id).tag("agent-runtime", task.id)
            if unit.startswith("day"):
                return builder.days.do(self._enqueue_job, task.id).tag("agent-runtime", task.id)
            raise ValueError(f"Unsupported schedule unit: {unit}")

        # Fall back to polling-based cron evaluation once per minute.
        return schedule.every(1).minutes.do(self._enqueue_job_if_due, task.id).tag("agent-runtime", task.id)

    def _enqueue_job(self, task_id: str):
        state = self._states.get(task_id)
        if not state:
            return
        self._running_jobs[task_id] = asyncio.create_task(self._execute_task(state.task))

    def _enqueue_job_if_due(self, task_id: str):
        state = self._states.get(task_id)
        if not state or not state.task.next_run:
            return
        due = self._parse_datetime(state.task.next_run)
        if due and due <= datetime.now(timezone.utc):
            self._running_jobs[task_id] = asyncio.create_task(self._execute_task(state.task))

    async def _execute_task(self, task: AgentScheduledTask) -> Dict[str, Any]:
        if self.runtime is None or self.memory_curation is None:
            raise RuntimeError("Scheduler is not bound to the runtime")

        result: Dict[str, Any]
        if task.task_type == "memory_curation":
            result = await self.memory_curation.curate_agent_memory(
                task.agent_id,
                frequency=str(task.config.get("frequency") or "daily"),
            )
        elif task.task_type == "data_cleanup":
            result = await self.runtime.run_background_task(
                agent_id=task.agent_id,
                message=str(task.config.get("prompt") or "Clean up outdated working data and summarize any deletions."),
                shared_context=task.config.get("shared_context") or {},
                timeout_seconds=int(task.config.get("timeout_seconds") or 120),
                metadata={"scheduled_task_id": task.id, "task_type": task.task_type},
            )
        else:
            result = await self.runtime.run_background_task(
                agent_id=task.agent_id,
                message=str(task.config.get("prompt") or f"Run scheduled task: {task.name}"),
                shared_context=task.config.get("shared_context") or {},
                timeout_seconds=int(task.config.get("timeout_seconds") or 120),
                metadata={"scheduled_task_id": task.id, "task_type": task.task_type},
            )

        last_run = utc_now_iso()
        next_run = self._compute_next_run(task.cron_expression)
        task.last_run = last_run
        task.next_run = next_run
        await sqlite_manager.update_agent_scheduled_task_run(task.id, last_run=last_run, next_run=next_run)
        self._states[task.id] = ScheduledTaskState(task=task, job=self._states.get(task.id).job if self._states.get(task.id) else None)
        return {"task": task.model_dump(), "result": result}

    def _compute_next_run(self, expression: str) -> Optional[str]:
        now = datetime.now(timezone.utc)
        lower = expression.strip().lower()
        if lower.startswith("every "):
            parts = lower.split()
            if len(parts) != 3 or not parts[1].isdigit():
                return None
            count = int(parts[1])
            unit = parts[2]
            if unit.startswith("minute"):
                return (now + timedelta(minutes=count)).isoformat()
            if unit.startswith("hour"):
                return (now + timedelta(hours=count)).isoformat()
            if unit.startswith("day"):
                return (now + timedelta(days=count)).isoformat()
            return None
        return self._compute_next_cron_run(expression, now)

    def _compute_next_cron_run(self, expression: str, now: datetime) -> Optional[str]:
        parts = expression.split()
        if len(parts) != 5:
            return None
        minute, hour, day, month, weekday = parts
        candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(60 * 24 * 366):
            if self._cron_matches(candidate, minute, hour, day, month, weekday):
                return candidate.isoformat()
            candidate += timedelta(minutes=1)
        return None

    def _cron_matches(self, dt: datetime, minute: str, hour: str, day: str, month: str, weekday: str) -> bool:
        return all(
            [
                self._cron_field_matches(dt.minute, minute),
                self._cron_field_matches(dt.hour, hour),
                self._cron_field_matches(dt.day, day),
                self._cron_field_matches(dt.month, month),
                self._cron_field_matches(dt.weekday(), weekday),
            ]
        )

    def _cron_field_matches(self, value: int, field: str) -> bool:
        if field == "*":
            return True
        if field.isdigit():
            return value == int(field)
        return False

    def _parse_datetime(self, value: str | None) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
