"""EmailProvider abstraction (BUILD_SPEC section 64)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lifeops.domain.email import EmailMessage, EmailSendDraft, EmailThread


@runtime_checkable
class EmailProvider(Protocol):
    async def search(self, query: str, *, limit: int = 25) -> list[EmailMessage]:
        """Section 64's search/read."""
        ...

    async def read_thread(self, thread_id: str) -> EmailThread:
        """Section 64's thread read."""
        ...

    async def send(self, draft: EmailSendDraft) -> str:
        """Section 64's send/reply. Returns the provider's message id — never
        a LifeOps-generated value, so a caller can tell the provider actually
        accepted it."""
        ...

    async def confirm_sent(self, message_id: str) -> bool:
        """Independent confirmation a sent message really left, e.g. by
        checking the Sent folder. Backs the same "do not trust the send call
        alone" discipline section 63 states for calendar bookings."""
        ...

    async def health(self) -> tuple[bool, str]: ...
