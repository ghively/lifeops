"""Backup and restore, proven (BUILD_SPEC sections 79, 80, 99).

OPERATIONS.md says "a backup is not complete until a restore has been
tested." This suite makes that literally true by driving the real scripts
against a disposable NornicDB instance: write known state, run
``scripts/backup.sh``, destroy the original data, run ``scripts/restore.sh``
into a fresh location, boot NornicDB against the restored data, and assert
the known state reads back exactly.

It never touches ``~/.local/share/lifeops`` — every LifeOps home used here is
a ``tmp_path`` subdirectory driven through its own ``LIFEOPS_HOME`` and its
own free Bolt/HTTP ports, entirely separate from any NornicDB instance a
developer or CI runner already has going. It skips cleanly, rather than
failing, when the NornicDB binary is not present to spin one up.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.domain.preferences import PreferenceDraft
from lifeops.errors import RepositoryError
from lifeops.policy import HERMES
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.secrets.local_encrypted import LocalEncryptedSecretStore
from lifeops.settings import Settings

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

REPO_ROOT = Path(__file__).resolve().parents[2]
NORNIC_BIN = Path(os.environ.get("NORNIC_BIN", str(Path.home() / ".local/lib/lifeops/nornicdb")))
NORNICDB_SH = REPO_ROOT / "scripts" / "nornicdb.sh"
BACKUP_SH = REPO_ROOT / "scripts" / "backup.sh"
RESTORE_SH = REPO_ROOT / "scripts" / "restore.sh"

PERSON_ID = "person_backup_restore_test"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, check=True, capture_output=True, text=True, timeout=90)


class _EphemeralNornic:
    """One disposable NornicDB process, started and stopped through the real
    ``scripts/nornicdb.sh`` — this suite proves the operator scripts, not a
    reimplementation of what they do."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.http_port = _free_port()
        self.bolt_port = _free_port()
        # NornicDB's telemetry listener port is fixed at 9090 unless told
        # otherwise, which collides with any other instance already running
        # on the machine (e.g. a developer's own `make dev`). Give this
        # disposable instance its own.
        self.telemetry_port = _free_port()

    @property
    def _env(self) -> dict[str, str]:
        return {
            **os.environ,
            "LIFEOPS_HOME": str(self.home),
            "LIFEOPS_NORNIC_HTTP_PORT": str(self.http_port),
            "LIFEOPS_NORNIC_BOLT_PORT": str(self.bolt_port),
            "NORNICDB_TELEMETRY_PORT": str(self.telemetry_port),
            "NORNICDB_TELEMETRY_LISTEN": f":{self.telemetry_port}",
        }

    def start(self) -> None:
        _run([str(NORNICDB_SH), "start"], env=self._env)

    def stop(self) -> None:
        subprocess.run(
            [str(NORNICDB_SH), "stop"], env=self._env, capture_output=True, text=True, timeout=30
        )

    def admin_password(self) -> str:
        for line in (self.home / "nornicdb.env").read_text().splitlines():
            if line.startswith("LIFEOPS_NORNIC_PASSWORD="):
                return line.split("=", 1)[1]
        raise RuntimeError(f"no admin password recorded in {self.home / 'nornicdb.env'}")

    def settings(self, state_dir: Path) -> Settings:
        return Settings(
            nornic_uri=f"bolt://127.0.0.1:{self.bolt_port}",
            nornic_user="admin",
            nornic_password=self.admin_password(),
            state_dir=state_dir,
        )


@pytest.fixture
def _require_nornic_binary() -> None:
    if not NORNIC_BIN.exists():
        pytest.skip(
            f"NornicDB binary not found at {NORNIC_BIN}; "
            "build it with ./scripts/build-nornicdb.sh to run this test"
        )


async def _write_known_state(instance: _EphemeralNornic, state_dir: Path) -> None:
    client = NornicClient(instance.settings(state_dir))
    try:
        await client.connect()
    except RepositoryError as exc:
        pytest.skip(f"isolated NornicDB instance did not come up: {exc}")
    try:
        await client.ensure_schema()
        people = NornicPersonRepository(client)
        preferences = NornicPreferenceRepository(client)
        tasks = NornicTaskRepository(client)
        core = LifeOpsCore(
            people=people, preferences=preferences, tasks=tasks, clock=FrozenClock()
        )

        await people.upsert(
            Person(
                id=PERSON_ID,
                display_name="Backup Restore Test Subject",
                is_primary=True,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling", value="after 10am", subject_id=PERSON_ID
            ),
        )
    finally:
        await client.close()


async def _assert_known_state(instance: _EphemeralNornic, state_dir: Path) -> None:
    client = NornicClient(instance.settings(state_dir))
    await client.connect()
    try:
        people = NornicPersonRepository(client)
        preferences = NornicPreferenceRepository(client)

        person = await people.get(PERSON_ID)
        assert person is not None, "the restored database is missing the known person"
        assert person.display_name == "Backup Restore Test Subject"

        current = await preferences.list_current(PERSON_ID)
        assert [p.value for p in current] == ["after 10am"]
    finally:
        await client.close()


class TestBackupRestoreRoundTrip:
    async def test_known_state_survives_backup_then_restore(
        self, _require_nornic_binary: None, tmp_path: Path
    ) -> None:
        original_home = tmp_path / "original"
        restored_home = tmp_path / "restored"
        backup_dest = tmp_path / "backup"
        original_home.mkdir()

        original = _EphemeralNornic(original_home)
        try:
            original.start()
        except subprocess.CalledProcessError as exc:
            pytest.skip(f"could not start an isolated NornicDB instance: {exc.stderr}")

        try:
            await _write_known_state(original, original_home / "core-state")

            # A real deployment also has non-secret configuration on disk;
            # exercise that half of backup.sh too.
            (original_home / "config").mkdir(exist_ok=True)
            (original_home / "config" / "lifeops.config.json").write_text(
                json.dumps({"system": {"display_name": "Backup Restore Test"}})
            )

            # And an encrypted secret, to exercise the vault + master key half
            # of backup.sh — the part that has to survive separated across
            # secrets/secrets.json and secret-master-key/master.key and still
            # decrypt once reunited by restore.sh.
            secret_store = LocalEncryptedSecretStore(original_home / "secrets")
            secret_store.set("deepseek_api_key", "sk-known-value-for-round-trip")

            # backup.sh stops and restarts NornicDB around the copy, so it
            # needs the same port/telemetry environment the instance was
            # actually started with — exactly what an operator's shell would
            # already have exported when running it by hand.
            backup_run = _run([str(BACKUP_SH), str(backup_dest)], env=original._env)
        finally:
            original.stop()

        assert (backup_dest / "nornicdb-data").is_dir(), backup_run.stdout
        assert (backup_dest / "nornicdb.env").is_file()
        assert (backup_dest / "config").is_dir()

        manifest = json.loads((backup_dest / "manifest.json").read_text())
        assert manifest["includes"]["nornicdb_data"] is True
        assert manifest["includes"]["nornicdb_env"] is True
        assert manifest["includes"]["secrets"] is True
        assert manifest["includes"]["secret_master_key"] is True

        # The master key lives in its own subtree, separated from the vault
        # it decrypts (BUILD_SPEC section 79: "back up separately").
        assert (backup_dest / "secrets" / "secrets.json").is_file()
        assert (backup_dest / "secret-master-key" / "master.key").is_file()

        # Destroy the original data — this is the failure the backup exists
        # for, so the round trip is meaningless unless the original is
        # actually gone before the restore runs.
        shutil.rmtree(original_home / "nornicdb-data")
        assert not (original_home / "nornicdb-data").exists()

        restore_env = {**os.environ}
        _run([str(RESTORE_SH), str(backup_dest), str(restored_home)], env=restore_env)

        assert (restored_home / "nornicdb-data").is_dir()
        assert (restored_home / "nornicdb.env").is_file()
        restored_config = json.loads(
            (restored_home / "config" / "lifeops.config.json").read_text()
        )
        assert restored_config["system"]["display_name"] == "Backup Restore Test"

        # The vault and its master key were restored back together and still
        # decrypt — proof the "back up separately" split does not silently
        # break restore when both halves are supplied.
        restored_secret_store = LocalEncryptedSecretStore(restored_home / "secrets")
        assert restored_secret_store.get("deepseek_api_key") == "sk-known-value-for-round-trip"

        restored = _EphemeralNornic(restored_home)
        try:
            restored.start()
        except subprocess.CalledProcessError as exc:
            pytest.fail(f"the restored NornicDB data would not start: {exc.stderr}")

        try:
            # If nornicdb.env had not been restored alongside the data, this
            # connection would fail authentication (CLAUDE.md: the admin
            # password is fixed at data-directory initialisation).
            await _assert_known_state(restored, restored_home / "core-state")
        finally:
            restored.stop()

    def test_restore_refuses_a_nonempty_destination_without_force(
        self, _require_nornic_binary: None, tmp_path: Path
    ) -> None:
        backup_dest = tmp_path / "backup"
        backup_dest.mkdir()
        (backup_dest / "manifest.json").write_text("{}")

        occupied = tmp_path / "occupied"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("do not clobber me")

        result = subprocess.run(
            [str(RESTORE_SH), str(backup_dest), str(occupied)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert (occupied / "keep.txt").read_text() == "do not clobber me"

    def test_backup_refuses_to_overwrite_an_existing_destination(
        self, _require_nornic_binary: None, tmp_path: Path
    ) -> None:
        source_home = tmp_path / "home"
        source_home.mkdir()

        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "keep.txt").write_text("already here")

        result = subprocess.run(
            [str(BACKUP_SH), str(dest)],
            env={**os.environ, "LIFEOPS_HOME": str(source_home)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert (dest / "keep.txt").read_text() == "already here"
