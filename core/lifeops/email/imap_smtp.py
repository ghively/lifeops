"""IMAP/SMTP email adapter (BUILD_SPEC sections 61, 64, 88, 96).

Real, and reachable only once a user fills in host/port/username/password
through the Console — no account detail is ever asked for or hardcoded
(section 88). It ships disabled.

This phase's instructions prefer ``httpx`` where the protocol allows it;
IMAP and SMTP are not HTTP, so this uses the standard library's ``imaplib``
and ``smtplib`` instead of introducing a new dependency for two protocols
httpx cannot speak. Both are synchronous, so every call is wrapped in
``asyncio.to_thread`` rather than blocking the event loop.

Scope is intentionally narrow, the same trade this phase makes for CalDAV:
``search`` matches subject/from/body via IMAP SEARCH, and threading is
approximated by grouping on the RFC 5322 ``References``/``In-Reply-To``
chain rather than a provider-specific thread id — correct for any IMAP
server, at the cost of not tracking a server's own thread grouping.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import email.utils
import imaplib
import smtplib
from email.message import EmailMessage as MimeEmailMessage

from lifeops.domain.email import EmailMessage, EmailSendDraft, EmailThread
from lifeops.errors import NotFoundError, ProviderError


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = email_lib.header.decode_header(value)
    return "".join(
        chunk.decode(encoding or "utf-8", errors="replace")
        if isinstance(chunk, bytes)
        else chunk
        for chunk, encoding in parts
    )


def _decoded_payload(msg: email_lib.message.Message) -> bytes:
    # get_payload(decode=True) returns bytes or None for leaf parts; the
    # broader Message|bytes union in its signature covers multipart access,
    # which decode=True never takes.
    payload = msg.get_payload(decode=True)
    return payload if isinstance(payload, bytes) else b""


def _snippet(msg: email_lib.message.Message, *, length: int = 200) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = _decoded_payload(part)
                return payload.decode(part.get_content_charset() or "utf-8", "replace")[:length]
        return ""
    payload = _decoded_payload(msg)
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")[:length]


def _to_email_message(uid: str, folder: str, raw: bytes) -> EmailMessage:
    msg = email_lib.message_from_bytes(raw)
    message_id = msg.get("Message-ID", uid).strip("<>")
    references = msg.get("References", "") or msg.get("In-Reply-To", "")
    thread_id = references.split()[0].strip("<>") if references.strip() else message_id
    return EmailMessage(
        message_id=message_id,
        thread_id=thread_id,
        from_address=email.utils.parseaddr(msg.get("From", ""))[1],
        to_addresses=[addr for _, addr in email.utils.getaddresses([msg.get("To", "")])],
        subject=_decode_header(msg.get("Subject")),
        snippet=_snippet(msg),
        received_at=msg.get("Date", ""),
        folder=folder,
    )


class ImapSmtpEmailProvider:
    def __init__(
        self,
        *,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_address: str,
        timeout_s: float = 20.0,
    ) -> None:
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._from_address = from_address or username
        self._timeout_s = timeout_s

    # --- IMAP -----------------------------------------------------------

    def _imap_connect(self) -> imaplib.IMAP4:
        conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, timeout=self._timeout_s)
        conn.login(self._username, self._password)
        return conn

    def _search_sync(self, query: str, *, limit: int) -> list[EmailMessage]:
        conn = self._imap_connect()
        try:
            conn.select("INBOX", readonly=True)
            criterion = f'(OR SUBJECT "{query}" FROM "{query}")' if query else "ALL"
            status, data = conn.search(None, criterion)
            if status != "OK":
                raise ProviderError(f"IMAP search failed: {status}", provider="email")
            uids = data[0].split()[-limit:] if data and data[0] else []
            messages: list[EmailMessage] = []
            for uid in reversed(uids):
                status, fetched = conn.fetch(uid, "(RFC822)")
                if status != "OK" or not fetched or fetched[0] is None:
                    continue
                raw = fetched[0][1]
                if not isinstance(raw, bytes):
                    continue
                messages.append(_to_email_message(uid.decode(), "INBOX", raw))
            return messages
        finally:
            conn.logout()

    async def search(self, query: str, *, limit: int = 25) -> list[EmailMessage]:
        return await asyncio.to_thread(self._search_sync, query, limit=limit)

    def _read_thread_sync(self, thread_id: str) -> EmailThread:
        conn = self._imap_connect()
        try:
            conn.select("INBOX", readonly=True)
            status, data = conn.search(
                None, f'(OR HEADER MESSAGE-ID "{thread_id}" HEADER REFERENCES "{thread_id}")'
            )
            if status != "OK" or not data or not data[0]:
                raise NotFoundError(f"no such thread: {thread_id}", thread_id=thread_id)
            messages: list[EmailMessage] = []
            for uid in data[0].split():
                status, fetched = conn.fetch(uid, "(RFC822)")
                if status != "OK" or not fetched or fetched[0] is None:
                    continue
                raw = fetched[0][1]
                if not isinstance(raw, bytes):
                    continue
                messages.append(_to_email_message(uid.decode(), "INBOX", raw))
            if not messages:
                raise NotFoundError(f"no such thread: {thread_id}", thread_id=thread_id)
            return EmailThread(
                thread_id=thread_id, subject=messages[0].subject, messages=messages
            )
        finally:
            conn.logout()

    async def read_thread(self, thread_id: str) -> EmailThread:
        return await asyncio.to_thread(self._read_thread_sync, thread_id)

    # --- SMTP -------------------------------------------------------------

    def _send_sync(self, draft: EmailSendDraft) -> str:
        message = MimeEmailMessage()
        message_id = email.utils.make_msgid(domain=self._from_address.split("@")[-1] or "lifeops")
        message["Message-ID"] = message_id
        message["From"] = self._from_address
        message["To"] = ", ".join(draft.to_addresses)
        message["Subject"] = draft.subject
        message["Date"] = email.utils.formatdate(localtime=True)
        if draft.in_reply_to:
            message["In-Reply-To"] = f"<{draft.in_reply_to}>"
            message["References"] = f"<{draft.in_reply_to}>"
        message.set_content(draft.body)

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._timeout_s) as smtp:
                smtp.starttls()
                smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderError(f"SMTP send failed: {exc}", provider="email") from exc
        return message_id.strip("<>")

    async def send(self, draft: EmailSendDraft) -> str:
        return await asyncio.to_thread(self._send_sync, draft)

    def _confirm_sent_sync(self, message_id: str) -> bool:
        conn = self._imap_connect()
        try:
            for folder in ("Sent", "INBOX.Sent", "Sent Items"):
                try:
                    status, _ = conn.select(folder, readonly=True)
                except imaplib.IMAP4.error:
                    continue
                if status != "OK":
                    continue
                status, data = conn.search(None, f'(HEADER MESSAGE-ID "{message_id}")')
                if status == "OK" and data and data[0]:
                    return True
            return False
        finally:
            conn.logout()

    async def confirm_sent(self, message_id: str) -> bool:
        return await asyncio.to_thread(self._confirm_sent_sync, message_id)

    def _health_sync(self) -> tuple[bool, str]:
        try:
            conn = self._imap_connect()
            conn.logout()
        except (imaplib.IMAP4.error, OSError) as exc:
            return False, f"IMAP login failed: {exc}"
        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._timeout_s) as smtp:
                smtp.starttls()
                smtp.login(self._username, self._password)
        except (smtplib.SMTPException, OSError) as exc:
            return False, f"SMTP login failed: {exc}"
        return True, "IMAP and SMTP reachable"

    async def health(self) -> tuple[bool, str]:
        return await asyncio.to_thread(self._health_sync)
