"""Email domain rules (BUILD_SPEC sections 61, 64, 96).

Pure functions only. Section 61 is the reason there is no
``make_idempotency_key`` here: the send payload is built for
``domain.actions.prepare``, which derives the key from the payload — this
module's job stops at producing that payload correctly.
"""

from __future__ import annotations

import pytest

from lifeops.domain.email import EmailSendDraft, build_send_payload, validate_send_draft
from lifeops.errors import ValidationError


def _draft(**overrides: object) -> EmailSendDraft:
    base = dict(
        to_addresses=["provider@example.com"],
        subject="Availability request",
        body="Do you have anything next week?",
    )
    return EmailSendDraft(**{**base, **overrides})


class TestAddressValidation:
    def test_a_well_formed_address_passes(self) -> None:
        validate_send_draft(_draft(to_addresses=["a@example.com", "b@example.com"]))

    def test_an_address_without_an_at_sign_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_send_draft(_draft(to_addresses=["not-an-address"]))

    def test_an_address_with_embedded_whitespace_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_send_draft(_draft(to_addresses=["a b@example.com"]))


class TestReplyShape:
    def test_a_reply_needs_both_thread_id_and_in_reply_to(self) -> None:
        with pytest.raises(ValidationError):
            validate_send_draft(_draft(thread_id="thread-1"))
        with pytest.raises(ValidationError):
            validate_send_draft(_draft(in_reply_to="msg-1"))

    def test_a_reply_with_both_is_accepted(self) -> None:
        validate_send_draft(_draft(thread_id="thread-1", in_reply_to="msg-1"))

    def test_a_new_message_needs_neither(self) -> None:
        validate_send_draft(_draft())


class TestSendPayload:
    def test_a_new_message_payload_carries_no_thread_fields(self) -> None:
        payload = build_send_payload(_draft())
        assert "thread_id" not in payload
        assert "in_reply_to" not in payload

    def test_a_reply_payload_carries_the_thread_fields(self) -> None:
        payload = build_send_payload(
            _draft(thread_id="thread-1", in_reply_to="msg-1")
        )
        assert payload["thread_id"] == "thread-1"
        assert payload["in_reply_to"] == "msg-1"

    def test_the_payload_is_exactly_what_goes_out(self) -> None:
        """Section 60: the approval screen renders this payload verbatim, so
        it must contain the whole request and nothing extra (task_id and
        target_entity_id travel on the Action record itself, not the
        payload)."""
        payload = build_send_payload(_draft(task_id="task_01"))
        assert "task_id" not in payload
        assert payload == {
            "to_addresses": ["provider@example.com"],
            "subject": "Availability request",
            "body": "Do you have anything next week?",
        }
