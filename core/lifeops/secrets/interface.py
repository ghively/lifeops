"""SecretStore interface (BUILD_SPEC section 24).

Secrets never enter NornicDB. Nornic holds the user's world model, which is
read broadly by agents and rendered in the Console; API keys and refresh
tokens have no business in that blast radius.

The interface is intentionally tiny. A Bitwarden backend arrives later without
changing a caller.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretStore(Protocol):
    def get(self, name: str) -> str | None:
        """Return the plaintext secret, or None if it is not set."""
        ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> bool:
        """Return True if a secret was removed."""
        ...

    def exists(self, name: str) -> bool: ...

    def list_names(self) -> list[str]:
        """Names only. Never values — this feeds the Console's
        configured/not-configured display."""
        ...

    def fingerprint(self, name: str) -> str | None:
        """A short non-reversible identifier for a stored secret.

        Lets a human confirm *which* key is installed without the value being
        readable. None when the secret is not set.
        """
        ...


def secret_ref(provider_id: str, field: str) -> str:
    """Canonical secret name for a provider field, e.g. ``elevenlabs.api_key``."""
    return f"{provider_id}.{field}"
