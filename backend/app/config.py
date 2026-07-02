# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for config."""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Represent settings."""
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
    generation_model: str = "google/flan-t5-base"
    nightly_training_mode: str = "dataset"
    model_output_dir: str = "/tmp/study-models"
    minimum_training_examples: int = 20
    training_interval_hours: int = 48
    training_epochs: int = 3
    training_learning_rate: float = 2e-5
    training_weight_decay: float = 0.01
    training_dropout: float = 0.25
    training_label_smoothing: float = 0.1
    training_batch_size: int = 8
    training_seed: int = 42
    training_thread_workers: int = 2
    submission_correction_minutes: int = 15
    upload_max_bytes: int = 26214400
    pdf_max_pages: int = 500
    audio_model: str = "openai/whisper-tiny"
    audio_max_seconds: int = 600
    inference_timeout_seconds: int = 120
    password_auth_enabled: bool = True
    client_certificate_auth_enabled: bool = True
    signature_hash_algorithm: str = "SHA-256"
    signature_algorithms: str = "Ed25519,ECDSA-SHA256,RSA-PSS-SHA256"
    certificate_default_valid_days: int = 365
    training_early_stopping_patience: int = 2
    training_early_stopping_min_delta: float = 0.0001
    internet_search_endpoint: str | None = None
    internet_search_api_key: SecretStr = SecretStr("")
    internet_search_timeout_seconds: int = 20
    trusted_fact_source_domains: str = "wikipedia.org,loc.gov,britannica.com,europa.eu,nist.gov,gov,edu"
    grammar_service_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    email_from: str = "no-reply@example.invalid"
    support_email: str | None = None
    allowed_free_models: str = (
        "google-bert/bert-base-multilingual-cased,FacebookAI/xlm-roberta-base,"
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2,"
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2,"
        "google/flan-t5-base,openai/whisper-tiny,MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
    )

    def require_allowed_model(self, model_id: str) -> str:
        """Reject model identifiers outside the approved free-model list."""
        allowed = {value.strip() for value in self.allowed_free_models.split(",") if value.strip()}
        if model_id not in allowed and not model_id.startswith(self.model_output_dir):
            raise ValueError(f"Model is not in ALLOWED_FREE_MODELS: {model_id}")
        return model_id


@lru_cache
def get_settings() -> Settings:
    """Perform the get settings operation."""
    return Settings()
