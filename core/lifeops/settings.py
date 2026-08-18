"""Boot settings for LifeOps Core.

These are *deployment* settings only: where the database lives, where state is
written, which ports to bind. They are deliberately NOT the place for provider
runtime configuration (DeepSeek keys, ElevenLabs voice IDs, Telegram tokens,
calendar accounts). All of that is configured by the user through LifeOps
Console at runtime and stored via the configuration service and SecretStore.

See CONFIGURATION.md for the split.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_state_dir() -> Path:
    """Durable LifeOps state lives outside the repository."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "lifeops"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIFEOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identity -----------------------------------------------------------
    display_name: str = "LifeOps"
    timezone: str = "UTC"

    # --- NornicDB (the single application/world-model database) -------------
    nornic_uri: str = "bolt://127.0.0.1:7687"
    nornic_user: str = "admin"
    nornic_password: str = Field(default="", repr=False)
    nornic_database: str | None = None
    nornic_http_url: str = "http://127.0.0.1:7474"
    nornic_connect_timeout_s: float = 10.0

    # --- LifeOps Core service -----------------------------------------------
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- State directories --------------------------------------------------
    state_dir: Path = Field(default_factory=_default_state_dir)
    # Where Code Change Requests land (BUILD_SPEC section 74). None means
    # resolve automatically: the repository's changes/requests/ when running
    # from a writable checkout, else a directory under state_dir — the MCP
    # server's working directory is whatever its client launched it with, so
    # a CWD-relative path would scatter requests (or fail under a read-only
    # deployment).
    change_requests_dir: Path | None = None

    # --- Behaviour ----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    # Safe mode disables every external write path (see BUILD_SPEC section 83).
    # Phase 0 has no external writes, but the flag exists from the start so
    # later phases inherit it rather than bolting it on.
    safe_mode: bool = False

    # --- Due-work worker (BUILD_SPEC section 55) -----------------------------
    # The "small LifeOps worker" that ticks over due WaitingItems. Interval is
    # a poll, not a promise: NornicDB holds the durable wake times, and this
    # is only how often the worker asks what is due now. Short in tests via
    # LIFEOPS_DUE_WORK_POLL_INTERVAL_S / an explicit Settings override.
    due_work_enabled: bool = True
    due_work_poll_interval_s: float = 60.0
    due_work_batch_limit: int = 50

    # --- Console authentication (SECURITY.md debt #1) ------------------------
    # Master switch for bearer-token auth on the Console API. Auth only
    # *applies* when a console password has also been set via the SecretStore
    # (core/lifeops/auth.py): with no password configured, a loopback-only
    # deployment stays open so first-run setup and tests work without a token.
    console_auth_enabled: bool = True

    @property
    def secrets_dir(self) -> Path:
        return self.state_dir / "secrets"

    @property
    def config_dir(self) -> Path:
        return self.state_dir / "config"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def change_requests_path(self) -> Path:
        """Where Code Change Requests are written (section 74).

        The repository's ``changes/requests/`` when this code runs from a
        writable checkout — a coding agent reads the repository, which is the
        point of the file format. Otherwise (installed package, read-only
        deployment) they land under ``state_dir`` where they can at least be
        collected.
        """
        if self.change_requests_dir is not None:
            return self.change_requests_dir
        repo_root = Path(__file__).resolve().parents[2]
        candidate = repo_root / "changes" / "requests"
        if candidate.parent.is_dir() and os.access(candidate.parent, os.W_OK):
            return candidate
        return self.state_dir / "change-requests"

    def ensure_dirs(self) -> None:
        for directory in (self.state_dir, self.secrets_dir, self.config_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        # Secrets directory must not be world- or group-readable.
        self.secrets_dir.chmod(0o700)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test hook — drops the cached Settings singleton."""
    get_settings.cache_clear()
