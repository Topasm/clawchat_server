from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/clawchat.db"

    # Authentication
    jwt_secret: str = "change-this-to-a-random-secret-key"
    jwt_expiry_hours: int = 24
    pin: str = "123456"

    # AI — delegates to OpenClaw gateway
    ai_base_url: str = "http://localhost:3000"
    ai_api_key: str = "openclaw"
    ai_model: str = "openclaw"

    # File uploads
    upload_dir: str = "data/uploads"
    max_upload_size_mb: int = 10
    allowed_extensions: str = "jpg,jpeg,png,gif,webp,svg,pdf,txt,md,zip"

    # Obsidian
    obsidian_vault_path: str = ""

    # Scheduler
    enable_scheduler: bool = False
    briefing_time: str = "08:00"
    reminder_check_interval: int = 5
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"debug", "development", "dev"}:
                return True
        return value


settings = Settings()
