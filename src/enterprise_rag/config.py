from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration, loaded from environment variables / .env.

    Every field has a safe local default so the app, tests, and CI can run
    fully offline without any paid API key or external service.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "Enterprise RAG"
    environment: str = "development"

    # LLM / embeddings
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    # Storage
    data_dir: Path = Path("data")
    database_url: str = "sqlite:///./data/enterprise_rag.db"
    chroma_persist_dir: str = "data/chroma"
    upload_dir: Path = Path("data/uploads")

    # Chunking
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 60

    # Auth
    jwt_secret: str = "change-me-in-production-use-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # Seeded admin account, created on first startup if it doesn't exist yet.
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me-in-production"

    # API
    api_base_url: str = "http://localhost:8000"
    cors_allow_origins: list[str] = ["http://localhost:8501"]

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_persist_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
