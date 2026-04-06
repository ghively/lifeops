"""Application Configuration"""
import os
from pathlib import Path
from typing import List


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
BACKUPS_DIR = BASE_DIR / "backups"
HEARTBEAT_FILE = BASE_DIR / "HEARTBEAT.md"


class Settings:
    """Application settings"""

    # Server settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    
    # Qdrant settings
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    
    # SQLite settings
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'knowledge_os.db').as_posix()}",
    )
    
    # OpenClaw settings
    openclaw_url: str = os.getenv(
        "OPENCLAW_URL",
        os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789"),
    )
    openclaw_token: str = os.getenv(
        "OPENCLAW_TOKEN",
        os.getenv("OPENCLAW_GATEWAY_TOKEN", ""),
    )
    
    # Backup settings
    data_dir: str = os.getenv("DATA_DIR", DATA_DIR.as_posix())
    backup_path: str = os.getenv("BACKUP_PATH", BACKUPS_DIR.as_posix())
    heartbeat_path: str = os.getenv("HEARTBEAT_PATH", HEARTBEAT_FILE.as_posix())
    
    # CORS settings
    @property
    def cors_origins(self) -> List[str]:
        """Get CORS origins from environment"""
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
        return [origin.strip() for origin in origins.split(",")]
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file_path: str = os.getenv(
        "LOG_FILE_PATH",
        str(Path(os.getenv("DATA_DIR", DATA_DIR.as_posix())) / "logs" / "app.log"),
    )
    
    # File watching
    watched_folders_path: str = os.getenv(
        "WATCHED_FOLDERS_PATH",
        f"{(DATA_DIR / 'watched_folders.json').as_posix()}",
    )
    
    # Git settings
    git_repo_url: str = os.getenv("GIT_REPO_URL", "")

    # LLM Provider settings (Agent Runtime)
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))

    # JWT/Authentication settings
    secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24h
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))  # 7 days
    reset_token_expire_hours: int = int(os.getenv("RESET_TOKEN_EXPIRE_HOURS", "1"))  # 1 hour


# Global settings instance
settings = Settings()
