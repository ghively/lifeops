"""Secret storage. Secrets never touch NornicDB (BUILD_SPEC section 24)."""

from lifeops.secrets.interface import SecretStore, secret_ref
from lifeops.secrets.local_encrypted import (
    InMemorySecretStore,
    LocalEncryptedSecretStore,
)

__all__ = [
    "InMemorySecretStore",
    "LocalEncryptedSecretStore",
    "SecretStore",
    "secret_ref",
]
