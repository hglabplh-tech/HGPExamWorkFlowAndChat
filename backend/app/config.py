from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://study:study@localhost:5432/study"
    jwt_secret: SecretStr = SecretStr("development-only-change-me-please")
    access_token_minutes: int = 15
    nonce_ttl_seconds: int = 3600
    signature_clock_skew_seconds: int = 300
    chroma_url: str = "http://localhost:8001"
    public_base_url: str = "https://localhost"
    retention_years: int = 10
    embedding_profile: str = "economy"
    embedding_model_economy: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_model_quality: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    reranker_model_mbert: str = "google-bert/bert-base-multilingual-cased"
    reranker_model_xlm_roberta: str = "FacebookAI/xlm-roberta-base"
    compute_device: str = "auto"
    eu_dss_validator_url: str | None = None
    trust_validation_timeout_seconds: int = 60
    ocsp_signer_url: str | None = None
    ocsp_signer_token: SecretStr = SecretStr("development-ocsp-token-change-me")
    nli_model: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"


@lru_cache
def get_settings() -> Settings:
    return Settings()
