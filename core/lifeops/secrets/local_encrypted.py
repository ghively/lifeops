"""LocalEncryptedSecretStore — the default, zero-dependency backend.

Design (BUILD_SPEC section 24):

  * AES-256-GCM, so tampering with the ciphertext is detected rather than
    producing garbage plaintext.
  * A random 32-byte master key, generated on first use, written 0600, and
    stored *outside* the Git repository.
  * Each secret gets a fresh 12-byte nonce. Reusing a nonce under one key is
    the standard way to break GCM, so it is never derived from the name.
  * The secret name is bound in as additional authenticated data, which stops
    a ciphertext being moved from one field to another inside the file.
  * Ciphertext lives in its own file, separate from NornicDB and from
    non-secret configuration.

The master key is the whole security boundary: anyone who can read it can read
every secret. It is backed up separately from the vault on purpose (section 79).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from lifeops.errors import SecretStoreError

_KEY_BYTES = 32
_NONCE_BYTES = 12
_VAULT_VERSION = 1


class LocalEncryptedSecretStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._key_path = directory / "master.key"
        self._vault_path = directory / "secrets.json"
        self._cache: dict[str, Any] | None = None
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o700)

    # --- master key ---------------------------------------------------------

    def _load_key(self) -> bytes:
        if self._key_path.exists():
            raw = self._key_path.read_bytes()
            key = base64.b64decode(raw)
            if len(key) != _KEY_BYTES:
                raise SecretStoreError(
                    "master key is malformed; refusing to continue",
                    path=str(self._key_path),
                )
            return key

        key = AESGCM.generate_key(bit_length=256)
        # Create with 0600 from the outset rather than chmod-ing afterwards:
        # a default-umask window is still a window.
        fd = os.open(self._key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, base64.b64encode(key))
        finally:
            os.close(fd)
        return key

    def rotate_master_key(self) -> None:
        """Re-encrypt every secret under a freshly generated master key."""
        plaintext = {name: self.get(name) for name in self.list_names()}
        self._key_path.unlink(missing_ok=True)
        self._cache = {"version": _VAULT_VERSION, "secrets": {}}
        self._write_vault(self._cache)
        for name, value in plaintext.items():
            if value is not None:
                self.set(name, value)

    # --- vault I/O ----------------------------------------------------------

    def _read_vault(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not self._vault_path.exists():
            self._cache = {"version": _VAULT_VERSION, "secrets": {}}
            return self._cache
        try:
            data = json.loads(self._vault_path.read_text())
        except json.JSONDecodeError as exc:
            raise SecretStoreError(
                "secret vault is corrupt", path=str(self._vault_path)
            ) from exc
        if data.get("version") != _VAULT_VERSION:
            raise SecretStoreError(
                f"unsupported secret vault version {data.get('version')!r}"
            )
        self._cache = data
        return data

    def _write_vault(self, data: dict[str, Any]) -> None:
        # Write-then-rename so an interrupted write cannot truncate the vault.
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, prefix=".secrets-", suffix=".tmp")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._vault_path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        os.chmod(self._vault_path, 0o600)
        self._cache = data

    # --- SecretStore --------------------------------------------------------

    def get(self, name: str) -> str | None:
        entry = self._read_vault()["secrets"].get(name)
        if entry is None:
            return None
        key = self._load_key()
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(
                base64.b64decode(entry["nonce"]),
                base64.b64decode(entry["ciphertext"]),
                name.encode("utf-8"),
            )
        except InvalidTag as exc:
            raise SecretStoreError(
                f"secret {name!r} failed authentication; the vault or master "
                "key may have been altered",
                name=name,
            ) from exc
        return plaintext.decode("utf-8")

    def set(self, name: str, value: str) -> None:
        if not name:
            raise SecretStoreError("secret name must not be empty")
        key = self._load_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), name.encode("utf-8"))

        vault = dict(self._read_vault())
        secrets = dict(vault["secrets"])
        secrets[name] = {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            # Stored rather than computed on read so that displaying the
            # fingerprint in the Console never requires decryption.
            "fingerprint": _fingerprint(value),
        }
        vault["secrets"] = secrets
        self._write_vault(vault)

    def delete(self, name: str) -> bool:
        vault = dict(self._read_vault())
        secrets = dict(vault["secrets"])
        if name not in secrets:
            return False
        del secrets[name]
        vault["secrets"] = secrets
        self._write_vault(vault)
        return True

    def exists(self, name: str) -> bool:
        return name in self._read_vault()["secrets"]

    def list_names(self) -> list[str]:
        return sorted(self._read_vault()["secrets"].keys())

    def fingerprint(self, name: str) -> str | None:
        entry = self._read_vault()["secrets"].get(name)
        return entry.get("fingerprint") if entry else None


def _fingerprint(value: str) -> str:
    """A short, non-reversible tag for a secret value.

    Salted with a fixed domain string so the digest is specific to this use and
    cannot be matched against a rainbow table of common API keys.
    """
    digest = hashlib.sha256(b"lifeops.secret.fingerprint:" + value.encode("utf-8"))
    return digest.hexdigest()[:12]


class InMemorySecretStore:
    """Test double. Nothing is persisted or encrypted."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> bool:
        return self._values.pop(name, None) is not None

    def exists(self, name: str) -> bool:
        return name in self._values

    def list_names(self) -> list[str]:
        return sorted(self._values)

    def fingerprint(self, name: str) -> str | None:
        value = self._values.get(name)
        return _fingerprint(value) if value is not None else None
