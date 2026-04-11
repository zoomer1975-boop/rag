from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "llama3.2:3b"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7

    # Embeddings
    embedding_base_url: str = "http://localhost:11434/v1"
    embedding_api_key: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = 768

    # Database
    database_url: str = "postgresql+asyncpg://raguser:ragpass@localhost:5432/ragdb"

    # Redis
    redis_url: str = "redis://localhost:6379"
    redis_session_ttl: int = 3600

    # App
    app_prefix: str = "/rag"
    secret_key: str = "change-me-to-a-random-secret-key"
    admin_username: str = "admin"
    admin_password: str = "change-me"

    # 다국어
    default_language: str = "ko"
    supported_languages: str = "ko,en,ja,zh,es,fr,de,pt,vi,th"

    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window: int = 60

    # 파일 업로드
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    @property
    def supported_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
