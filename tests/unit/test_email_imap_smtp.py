"""IMAP/SMTP adapter helpers (BUILD_SPEC sections 64, 96).

Pinned after the 2026-08-18 audit: SEARCH criteria were built by unescaped
f-string (quotes broke the grammar, any non-ASCII query raised
``UnicodeEncodeError``), mailbox names with spaces went unquoted (a protocol
error on every server), a bogus MIME charset crashed the whole search, and
``received_at`` was the raw RFC 2822 Date header — which sorts by weekday
name.
"""

from __future__ import annotations

from lifeops.email.imap_smtp import (
    _escape_search_text,
    _quote_mailbox,
    _safe_decode,
    _to_email_message,
)


class TestSearchEscaping:
    def test_quotes_and_backslashes_are_escaped(self) -> None:
        assert _escape_search_text('say "hi" \\ bye') == 'say \\"hi\\" \\\\ bye'

    def test_mailbox_names_with_spaces_are_quoted(self) -> None:
        assert _quote_mailbox("Sent Items") == '"Sent Items"'
        assert _quote_mailbox("[Gmail]/Sent Mail") == '"[Gmail]/Sent Mail"'


class TestCharsetSurvival:
    def test_a_bogus_charset_falls_back_instead_of_raising(self) -> None:
        assert _safe_decode("héllo".encode(), "cp-weird") == "héllo"

    def test_a_message_with_a_bogus_charset_still_parses(self) -> None:
        raw = (
            b"From: a@example.com\r\nTo: b@example.com\r\n"
            b"Subject: hello\r\nMessage-ID: <m1@example.com>\r\n"
            b"Date: Tue, 18 Aug 2026 09:30:00 +0200\r\n"
            b'Content-Type: text/plain; charset="x-no-such-charset"\r\n\r\n'
            b"body text\r\n"
        )
        message = _to_email_message("1", "INBOX", raw)
        assert message.snippet.startswith("body text")


class TestReceivedAt:
    def test_the_date_header_becomes_sortable_iso_utc(self) -> None:
        raw = (
            b"From: a@example.com\r\nMessage-ID: <m1@example.com>\r\n"
            b"Date: Tue, 18 Aug 2026 09:30:00 +0200\r\n\r\nhi\r\n"
        )
        message = _to_email_message("1", "INBOX", raw)
        assert message.received_at == "2026-08-18T07:30:00Z"

    def test_an_unparseable_date_passes_through_raw(self) -> None:
        raw = (
            b"From: a@example.com\r\nMessage-ID: <m1@example.com>\r\n"
            b"Date: not a date\r\n\r\nhi\r\n"
        )
        message = _to_email_message("1", "INBOX", raw)
        assert message.received_at == "not a date"


class TestDateOrderingIsChronological:
    def test_iso_dates_sort_chronologically_where_rfc2822_did_not(self) -> None:
        """The concrete failure: "Fri, 01 May" sorted before "Mon, 02 Mar"
        as a string. The ISO forms sort correctly."""
        first = _received_at_of(b"Date: Mon, 02 Mar 2026 10:00:00 +0000\r\n\r\n")
        second = _received_at_of(b"Date: Fri, 01 May 2026 10:00:00 +0000\r\n\r\n")
        assert first < second


def _received_at_of(tail: bytes) -> str:
    raw = b"From: a@example.com\r\nMessage-ID: <m@example.com>\r\n" + tail
    return _to_email_message("1", "INBOX", raw).received_at
