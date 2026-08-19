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
``search`` matches subject/from/body via IMAP ``TEXT`` SEARCH (RFC 3501:
headers plus body), and threading is approximated by grouping on the RFC
5322 ``References``/``In-Reply-To`` chain rather than a provider-specific
thread id — correct for any IMAP server, at the cost of not tracking a
server's own thread grouping.

Every IMAP failure surfaces as a structured ``ProviderError`` (the same
contract the Twilio and ElevenLabs adapters keep), never a raw
``imaplib.IMAP4.error`` that the API layer would report as an unhandled 500.
"""

from __future__ import annotations

import asyncio
import contextlib
import email as email_lib
import email.utils
import imaplib
import smtplib
import ssl
import time
from datetime import UTC
from email.message import EmailMessage as MimeEmailMessage
from typing import Any, cast

from lifeops.domain.email import EmailMessage, EmailSendDraft, EmailThread
from lifeops.errors import NotFoundError, ProviderError

#: Where sent mail lives, most-common first. ``[Gmail]/Sent Mail`` is where
#: Gmail actually auto-saves — its absence made ``confirm_sent`` permanently
#: False against the world's most common provider.
_SENT_FOLDERS = ("Sent", "Sent Items", "[Gmail]/Sent Mail", "INBOX.Sent")


def _quote_mailbox(name: str) -> str:
    """An IMAP mailbox name as a quoted string. imaplib does no quoting of
    its own, so an unquoted ``Sent Items`` went to the server as two tokens —
    a protocol error on every server."""
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _escape_search_text(value: str) -> str:
    """Escape a value for use inside an IMAP SEARCH quoted string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _safe_decode(payload: bytes, charset: str | None) -> str:
    """Decode with the message's advertised charset, surviving a bogus one.

    A message advertising ``charset=cp-weird`` raised an uncaught
    ``LookupError`` and took the whole search result down with it.
    """
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = email_lib.header.decode_header(value)
    return "".join(
        _safe_decode(chunk, encoding) if isinstance(chunk, bytes) else chunk
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
                return _safe_decode(payload, part.get_content_charset())[:length]
        return ""
    payload = _decoded_payload(msg)
    return _safe_decode(payload, msg.get_content_charset())[:length]


def _received_at(msg: email_lib.message.Message) -> str:
    """The Date header as ISO 8601 UTC, so consumers can sort it.

    The raw RFC 2822 form ("Fri, 01 May 2026 …") sorts alphabetically by
    weekday name — chronology-free — and the fake orders by this field.
    Falls back to the raw header only when it cannot be parsed at all.
    """
    raw = msg.get("Date", "")
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
        received_at=_received_at(msg),
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
        # An explicit verifying context is load-bearing: unlike the HTTP
        # stack, imaplib's (and smtplib's) default TLS context does NOT
        # verify server certificates, so without it the mailbox password
        # would complete a handshake with any active man-in-the-middle.
        try:
            conn = imaplib.IMAP4_SSL(
                self._imap_host,
                self._imap_port,
                timeout=self._timeout_s,
                ssl_context=ssl.create_default_context(),
            )
            conn.login(self._username, self._password)
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ProviderError(
                f"IMAP connection failed: {exc}", provider="email"
            ) from exc
        return conn

    @staticmethod
    def _logout_quietly(conn: imaplib.IMAP4) -> None:
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            conn.logout()

    @staticmethod
    def _issue_search(conn: imaplib.IMAP4, query: str) -> tuple[str, list[Any]]:
        """One SEARCH, safely. ``TEXT`` covers headers and body (RFC 3501),
        which is the subject/from/body promise of the module docstring. The
        query is escaped for the quoted-string grammar; a non-ASCII query —
        which imaplib cannot send inline at all — goes as a UTF-8 literal
        with an explicit CHARSET, instead of dying in ``UnicodeEncodeError``.
        """
        if not query:
            return conn.search(None, "ALL")
        try:
            escaped = _escape_search_text(query)
            escaped.encode("ascii")
        except UnicodeEncodeError:
            # typeshed types ``literal`` as str, but imaplib's own docs and
            # implementation require bytes here — cast rather than lie.
            conn.literal = cast(Any, query.encode("utf-8"))
            return conn.search("UTF-8", "TEXT")
        return conn.search(None, f'(TEXT "{escaped}")')

    def _search_sync(self, query: str, *, limit: int) -> list[EmailMessage]:
        conn = self._imap_connect()
        try:
            conn.select("INBOX", readonly=True)
            status, data = self._issue_search(conn, query)
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
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ProviderError(f"IMAP search failed: {exc}", provider="email") from exc
        finally:
            self._logout_quietly(conn)

    async def search(self, query: str, *, limit: int = 25) -> list[EmailMessage]:
        return await asyncio.to_thread(self._search_sync, query, limit=limit)

    def _read_thread_sync(self, thread_id: str) -> EmailThread:
        needle = _escape_search_text(thread_id)
        conn = self._imap_connect()
        try:
            conn.select("INBOX", readonly=True)
            status, data = conn.search(
                None,
                f'(OR HEADER MESSAGE-ID "{needle}" HEADER REFERENCES "{needle}")',
            )
            if status != "OK" or not data or not data[0]:
                raise NotFoundError(f"no such thread: {thread_id}", thread_id=thread_id)
            messages: list[EmailMessage] = []
            for uid in data[0].split():
                status, fetched = conn.fetch(uid.decode(), "(RFC822)")
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
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ProviderError(
                f"IMAP thread read failed: {exc}", provider="email"
            ) from exc
        finally:
            self._logout_quietly(conn)

    async def read_thread(self, thread_id: str) -> EmailThread:
        return await asyncio.to_thread(self._read_thread_sync, thread_id)

    # --- SMTP -------------------------------------------------------------

    def _smtp_connect(self) -> smtplib.SMTP:
        # Port 465 is implicit TLS: the handshake happens before any SMTP
        # command, so ``SMTP`` + ``starttls()`` can never work there —
        # ``SMTP_SSL`` is required. Every other port does STARTTLS. Both
        # verify certificates (see _imap_connect for why that is explicit).
        context = ssl.create_default_context()
        if self._smtp_port == 465:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                self._smtp_host,
                self._smtp_port,
                timeout=self._timeout_s,
                context=context,
            )
        else:
            smtp = smtplib.SMTP(
                self._smtp_host, self._smtp_port, timeout=self._timeout_s
            )
            smtp.starttls(context=context)
        smtp.login(self._username, self._password)
        return smtp

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
            with self._smtp_connect() as smtp:
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderError(f"SMTP send failed: {exc}", provider="email") from exc
        # SMTP delivered the message; nothing after this may unsay that.
        self._append_to_sent(bytes(message))
        return message_id.strip("<>")

    def _append_to_sent(self, raw: bytes) -> None:
        """Best-effort copy into a Sent folder after a successful send.

        SMTP does not save sent mail; outside Gmail-style servers that
        auto-save, nothing put the message anywhere ``confirm_sent`` could
        find it, so verification recorded a false "not found in the Sent
        folder" for every genuinely sent email. Failure here is swallowed
        deliberately: the send already happened, and a copy that could not
        be filed must not turn a delivered message into a reported failure.
        (On servers that auto-save, the APPEND may add a second copy; Gmail
        de-duplicates on Message-ID.)
        """
        try:
            conn = self._imap_connect()
        except ProviderError:
            return
        try:
            stamp = imaplib.Time2Internaldate(time.time())
            for folder in _SENT_FOLDERS:
                try:
                    status, _ = conn.append(
                        _quote_mailbox(folder), "(\\Seen)", stamp, raw
                    )
                except (imaplib.IMAP4.error, OSError):
                    continue
                if status == "OK":
                    return
        finally:
            self._logout_quietly(conn)

    async def send(self, draft: EmailSendDraft) -> str:
        return await asyncio.to_thread(self._send_sync, draft)

    def _confirm_sent_sync(self, message_id: str) -> bool:
        needle = _escape_search_text(message_id)
        conn = self._imap_connect()
        try:
            for folder in _SENT_FOLDERS:
                try:
                    status, _ = conn.select(_quote_mailbox(folder), readonly=True)
                except imaplib.IMAP4.error:
                    continue
                if status != "OK":
                    continue
                status, data = conn.search(None, f'(HEADER MESSAGE-ID "{needle}")')
                if status == "OK" and data and data[0]:
                    return True
            return False
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ProviderError(
                f"IMAP sent-folder check failed: {exc}", provider="email"
            ) from exc
        finally:
            self._logout_quietly(conn)

    async def confirm_sent(self, message_id: str) -> bool:
        return await asyncio.to_thread(self._confirm_sent_sync, message_id)

    def _health_sync(self) -> tuple[bool, str]:
        try:
            conn = self._imap_connect()
            self._logout_quietly(conn)
        except ProviderError as exc:
            return False, f"IMAP login failed: {exc}"
        try:
            with self._smtp_connect():
                pass
        except (smtplib.SMTPException, OSError) as exc:
            return False, f"SMTP login failed: {exc}"
        return True, "IMAP and SMTP reachable"

    async def health(self) -> tuple[bool, str]:
        return await asyncio.to_thread(self._health_sync)
