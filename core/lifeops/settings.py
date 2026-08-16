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

    # --- Behaviour ----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    # Safe mode disables every external write path (see BUILD_SPEC section 83).
    # Phase 0 has no external writes, but the flag exists from the start so
    # later phases inherit it rather than bolting it on.
    safe_mode: bool = False

    @property
    def secrets_dir(self) -> Path:
        return self.state_dir / "secrets"

    @property
    def config_dir(self) -> Path:
        return self.state_dir / "config"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

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
