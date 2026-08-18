"""Log redaction (BUILD_SPEC section 24: secrets never appear in a log).

The Console log sink feeds browser-supplied context through ``redact``, and
provider errors carry whatever shape the adapter raised with — so the
function has to survive shapes nobody planned for, not just flat dicts.
"""

from __future__ import annotations

from lifeops.observability.logging import redact

REDACTED = "<redacted>"


class TestRedact:
    def test_flat_keys(self) -> None:
        assert redact({"password": "hunter2", "user": "gene"}) == {
            "password": REDACTED,
            "user": "gene",
        }

    def test_nested_dicts(self) -> None:
        cleaned = redact({"smtp": {"password": "hunter2", "host": "mail"}})
        assert cleaned == {"smtp": {"password": REDACTED, "host": "mail"}}

    def test_dicts_inside_lists(self) -> None:
        """{"attempts": [{"password": ...}]} used to pass through untouched."""
        cleaned = redact({"attempts": [{"password": "hunter2", "n": 1}]})
        assert cleaned == {"attempts": [{"password": REDACTED, "n": 1}]}

    def test_prefixed_key_names(self) -> None:
        """Providers name fields smtp_password / elevenlabs_api_key; exact
        matching redacted neither."""
        cleaned = redact(
            {"smtp_password": "hunter2", "elevenlabs_api_key": "sk-123"}
        )
        assert cleaned == {
            "smtp_password": REDACTED,
            "elevenlabs_api_key": REDACTED,
        }

    def test_case_insensitive(self) -> None:
        assert redact({"Authorization": "Bearer x"}) == {
            "Authorization": REDACTED
        }

    def test_non_sensitive_values_pass_untouched(self) -> None:
        payload = {"count": 3, "items": ["a", "b"], "flag": True, "none": None}
        assert redact(payload) == payload
