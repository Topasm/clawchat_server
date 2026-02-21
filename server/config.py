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

    # AI Provider
    ai_provider: str = "ollama"
    ai_base_url: str = "http://localhost:11434"
    ai_api_key: str = ""
    ai_model: str = "llama3.2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
