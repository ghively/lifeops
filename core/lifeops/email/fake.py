"""FakeEmailProvider — deterministic in-memory mailbox for tests
(BUILD_SPEC sections 64, 88). Never reaches a real mail server."""

from __future__ import annotations

import itertools

from lifeops.domain.email import EmailMessage, EmailSendDraft, EmailThread
from lifeops.errors import NotFoundError


class FakeEmailProvider:
    def __init__(self) -> None:
        self._messages: dict[str, EmailMessage] = {}
        self._threads: dict[str, list[str]] = {}
        self._sent: set[str] = set()
        self._counter = itertools.count(1)
        self.healthy = True

    def seed(self, message: EmailMessage) -> None:
        """Place a message directly, for tests that need something to
        search or read before this adapter has sent anything itself."""
        self._messages[message.message_id] = message
        self._threads.setdefault(message.thread_id, []).append(message.message_id)

    async def search(self, query: str, *, limit: int = 25) -> list[EmailMessage]:
        needle = query.strip().lower()
        matches = [
            m
            for m in self._messages.values()
            if not needle
            or needle in m.subject.lower()
            or needle in m.snippet.lower()
            or needle in m.from_address.lower()
        ]
        return sorted(matches, key=lambda m: m.received_at, reverse=True)[:limit]

    async def read_thread(self, thread_id: str) -> EmailThread:
        message_ids = self._threads.get(thread_id)
        if not message_ids:
            raise NotFoundError(f"no such thread: {thread_id}", thread_id=thread_id)
        messages = [self._messages[mid] for mid in message_ids]
        return EmailThread(
            thread_id=thread_id, subject=messages[0].subject, messages=messages
        )

    async def send(self, draft: EmailSendDraft) -> str:
        message_id = f"fake-msg-{next(self._counter)}"
        thread_id = draft.thread_id or f"fake-thread-{message_id}"
        self._messages[message_id] = EmailMessage(
            message_id=message_id,
            thread_id=thread_id,
            from_address="me@example.invalid",
            to_addresses=list(draft.to_addresses),
            subject=draft.subject,
            snippet=draft.body[:200],
            folder="Sent",
        )
        self._threads.setdefault(thread_id, []).append(message_id)
        self._sent.add(message_id)
        return message_id

    async def confirm_sent(self, message_id: str) -> bool:
        return message_id in self._sent

    async def health(self) -> tuple[bool, str]:
        return self.healthy, "fake email provider" if self.healthy else "forced unhealthy"
