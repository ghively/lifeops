"""LocalEncryptedSecretStore: confidentiality, integrity, and file permissions."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from lifeops.errors import SecretStoreError
from lifeops.secrets.local_encrypted import LocalEncryptedSecretStore


class TestRoundTrip:
    def test_set_and_get(self, encrypted_store: LocalEncryptedSecretStore) -> None:
        encrypted_store.set("deepseek.api_key", "sk-secret-value")
        assert encrypted_store.get("deepseek.api_key") == "sk-secret-value"

    def test_missing_secret_is_none(self, encrypted_store: LocalEncryptedSecretStore) -> None:
        assert encrypted_store.get("nope") is None
        assert not encrypted_store.exists("nope")

    def test_overwrite(self, encrypted_store: LocalEncryptedSecretStore) -> None:
        encrypted_store.set("k", "first")
        encrypted_store.set("k", "second")
        assert encrypted_store.get("k") == "second"

    def test_delete(self, encrypted_store: LocalEncryptedSecretStore) -> None:
        encrypted_store.set("k", "v")
        assert encrypted_store.delete("k")
        assert not encrypted_store.delete("k")
        assert encrypted_store.get("k") is None

    def test_survives_a_new_store_instance(self, tmp_path: Path) -> None:
        directory = tmp_path / "secrets"
        LocalEncryptedSecretStore(directory).set("k", "durable")
        assert LocalEncryptedSecretStore(directory).get("k") == "durable"

    def test_unicode_values(self, encrypted_store: LocalEncryptedSecretStore) -> None:
        encrypted_store.set("k", "pässwörd-✓")
        assert encrypted_store.get("k") == "pässwörd-✓"


class TestConfidentiality:
    def test_plaintext_never_appears_on_disk(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("deepseek.api_key", "sk-super-secret-12345")
        for path in (tmp_path / "secrets").rglob("*"):
            if path.is_file():
                assert b"sk-super-secret-12345" not in path.read_bytes()

    def test_listing_exposes_names_only(
        self, encrypted_store: LocalEncryptedSecretStore
    ) -> None:
        encrypted_store.set("a.key", "value-a")
        encrypted_store.set("b.key", "value-b")
        assert encrypted_store.list_names() == ["a.key", "b.key"]

    def test_fingerprint_is_stable_and_not_the_value(
        self, encrypted_store: LocalEncryptedSecretStore
    ) -> None:
        encrypted_store.set("k", "value")
        fingerprint = encrypted_store.fingerprint("k")
        assert fingerprint is not None
        assert "value" not in fingerprint

        encrypted_store.set("k2", "value")
        assert encrypted_store.fingerprint("k2") == fingerprint

    def test_different_values_have_different_fingerprints(
        self, encrypted_store: LocalEncryptedSecretStore
    ) -> None:
        encrypted_store.set("a", "one")
        encrypted_store.set("b", "two")
        assert encrypted_store.fingerprint("a") != encrypted_store.fingerprint("b")

    def test_nonce_is_not_reused_across_secrets(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        # Nonce reuse under one AES-GCM key is a break, not a nitpick.
        for index in range(20):
            encrypted_store.set(f"k{index}", "same-value-every-time")
        vault = json.loads((tmp_path / "secrets" / "secrets.json").read_text())
        nonces = [entry["nonce"] for entry in vault["secrets"].values()]
        assert len(set(nonces)) == len(nonces)

    def test_identical_values_produce_different_ciphertext(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("a", "identical")
        encrypted_store.set("b", "identical")
        vault = json.loads((tmp_path / "secrets" / "secrets.json").read_text())
        assert (
            vault["secrets"]["a"]["ciphertext"] != vault["secrets"]["b"]["ciphertext"]
        )


class TestIntegrity:
    def test_tampered_ciphertext_is_rejected(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("k", "original")
        vault_path = tmp_path / "secrets" / "secrets.json"
        vault = json.loads(vault_path.read_text())

        ciphertext = vault["secrets"]["k"]["ciphertext"]
        # Flip a character so decryption fails authentication rather than
        # returning attacker-chosen plaintext.
        flipped = "B" if ciphertext[0] != "B" else "C"
        vault["secrets"]["k"]["ciphertext"] = flipped + ciphertext[1:]
        vault_path.write_text(json.dumps(vault))

        store = LocalEncryptedSecretStore(tmp_path / "secrets")
        with pytest.raises(SecretStoreError):
            store.get("k")

    def test_a_secret_cannot_be_moved_between_names(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        # The name is bound in as additional authenticated data, so relabelling
        # a ciphertext must not yield a valid secret under the new name.
        encrypted_store.set("elevenlabs.api_key", "voice-key")
        encrypted_store.set("deepseek.api_key", "llm-key")

        vault_path = tmp_path / "secrets" / "secrets.json"
        vault = json.loads(vault_path.read_text())
        vault["secrets"]["deepseek.api_key"] = vault["secrets"]["elevenlabs.api_key"]
        vault_path.write_text(json.dumps(vault))

        store = LocalEncryptedSecretStore(tmp_path / "secrets")
        with pytest.raises(SecretStoreError):
            store.get("deepseek.api_key")

    def test_corrupt_vault_raises_rather_than_silently_resetting(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "secrets"
        LocalEncryptedSecretStore(directory).set("k", "v")
        (directory / "secrets.json").write_text("{not json")

        with pytest.raises(SecretStoreError):
            LocalEncryptedSecretStore(directory).get("k")


class TestFilePermissions:
    def test_master_key_is_owner_only(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("k", "v")
        mode = stat.S_IMODE((tmp_path / "secrets" / "master.key").stat().st_mode)
        assert mode == 0o600

    def test_vault_is_owner_only(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("k", "v")
        mode = stat.S_IMODE((tmp_path / "secrets" / "secrets.json").stat().st_mode)
        assert mode == 0o600

    def test_directory_is_owner_only(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("k", "v")
        mode = stat.S_IMODE((tmp_path / "secrets").stat().st_mode)
        assert mode == 0o700

    def test_master_key_lives_outside_the_repository(self, tmp_path: Path) -> None:
        from lifeops.settings import Settings

        settings = Settings(state_dir=tmp_path / "state")
        repo_root = Path(__file__).resolve().parents[2]
        assert repo_root not in settings.secrets_dir.resolve().parents


class TestRotation:
    def test_rotation_preserves_every_secret(
        self, encrypted_store: LocalEncryptedSecretStore, tmp_path: Path
    ) -> None:
        encrypted_store.set("a", "value-a")
        encrypted_store.set("b", "value-b")
        key_before = (tmp_path / "secrets" / "master.key").read_bytes()

        encrypted_store.rotate_master_key()

        assert (tmp_path / "secrets" / "master.key").read_bytes() != key_before
        assert encrypted_store.get("a") == "value-a"
        assert encrypted_store.get("b") == "value-b"
