import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_DEFAULTS: dict[str, str] = {}

_REQUIRED_SECRETS = {
    "secret_key": "change-me-to-a-random-secret-key",
    "admin_password": "change-me",
    "admin_api_token": "",
}


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

    # Chunking — tiktoken과 임베딩 모델 토크나이저 차이를 고려해 여유 있게 설정
    chunk_size: int = 400
    chunk_overlap: int = 50

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
    admin_api_token: str = ""

    # 다국어
    default_language: str = "ko"
    supported_languages: str = "ko,en,ja,zh,es,fr,de,pt,vi,th"

    # CORS — 프로덕션에서는 실제 출처 목록으로 교체하세요 (예: ["https://example.com"])
    cors_allowed_origins: list[str] = ["*"]

    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window: int = 60

    # 파일 업로드
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # Jina Reader (URL 인제스트)
    jina_api_key: str = ""

    # GraphRAG
    graph_top_k_entities: int = 10
    graph_top_k_relationships: int = 10
    graph_neighbor_hops: int = 1
    graph_extraction_max_gleaning: int = 1

    # Safeguard (kanana-safeguard-prompt-2.1b via vLLM)
    safeguard_enabled: bool = False
    safeguard_base_url: str = "http://localhost:8001/v1"
    safeguard_api_key: str = "none"
    safeguard_model: str = "kakaocorp/kanana-safeguard-prompt-2.1b"
    safeguard_blocked_message: str = "**UNSAFE** 죄송합니다. 해당 메시지는 처리할 수 없습니다."
    safeguard_fail_open: bool = True

    # Tool calling — "auto": 모델 자율 선택 (Ollama 호환), "required": 첫 호출 강제 (Gemma4/vLLM)
    llm_tool_choice: str = "auto"

    # Reranker (cross-encoder, 로컬 모델)
    reranker_enabled: bool = False
    reranker_model: str = "dragonkue/bge-reranker-v2-m3-ko"
    reranker_top_n: int = 3
    reranker_device: str = "cuda"

    # PII Masker (NER, 로컬 모델)
    pii_ner_model: str = "monologg/koelectra-base-finetuned-naver-ner"
    pii_ner_device: str = "cpu"

    @property
    def supported_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # 기본값 그대로면 서버 기동 차단 (암호화 키 파생에 직접 사용됨)
    for field, insecure_val in _REQUIRED_SECRETS.items():
        if getattr(settings, field) == insecure_val or not getattr(settings, field):
            raise ValueError(
                f"[설정 오류] {field.upper()} 가 기본값이거나 비어 있습니다. "
                f".env 에서 반드시 변경하세요. "
                f"생성 예시: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    for field, insecure_val in _INSECURE_DEFAULTS.items():
        if getattr(settings, field) == insecure_val:
            logger.warning(
                "[보안 경고] %s 가 기본값으로 설정되어 있습니다. 프로덕션 환경에서는 반드시 변경하세요.",
                field.upper(),
            )
    if settings.cors_allowed_origins == ["*"]:
        logger.warning(
            "[보안 경고] CORS_ALLOWED_ORIGINS 가 와일드카드(*)로 설정되어 있습니다. "
            "프로덕션 환경에서는 실제 출처 목록으로 변경하세요. "
            "예: CORS_ALLOWED_ORIGINS=[\"https://example.com\"]"
        )
    return settings
