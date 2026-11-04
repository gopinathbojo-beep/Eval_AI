from __future__ import annotations
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import AliasChoices, Field, model_validator
from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

AI_UNAVAILABLE_MESSAGE = "OpenRouter is unavailable. Check the API key, the model name and the credit balance."
AI_BAD_RESPONSE_MESSAGE = "The AI model did not return a valid structured response. Review the document and retry."


def _root_oauth(name: str, legacy: str = "", default: str = "") -> str:
    # Legacy aliases remain supported when this module is used outside the normal settings loader.
    path = Path(__file__).resolve().parents[2] / ".env"
    values = {k.lower(): v for k, v in dotenv_values(path).items() if v} if path.exists() else {}
    return values.get(name.lower(), values.get(legacy.lower(), default))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(Path(__file__).resolve().parents[2] / ".env"), str(Path(__file__).resolve().parents[1] / ".env")), extra="ignore", hide_input_in_errors=True)

    database_url: str = ""
    database_sslmode: str = "require"
    storage_provider: Literal["local", "supabase"] = "local"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "eval-ai-documents"
    storage_timeout: int = 120
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-3.5-flash-lite"
    openrouter_base_url: str = "https://openrouter.ai/api"
    ai_request_logprobs: bool = False
    # OCR transcribes source evidence; reserve output tokens for the document.
    # Text-only grading retains the model's own reasoning defaults.
    ai_ocr_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "minimal"
    ai_text_reasoning_effort: Literal["low", "high"] = "low"
    ai_timeout: int = 300
    ai_max_retries: int = 2
    ai_max_output_tokens: int = 8192
    ai_parallel_jobs: int = 1
    # local embeddings for the reference library (fastembed, CPU); empty = keyword search only
    reference_embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # textbook passages shown to the grader as read-only reference
    reference_in_grading: bool = True
    durable_jobs: bool = False
    auto_migrate: bool = False
    public_web_url: str = ""

    @model_validator(mode="after")
    def cloud_settings(self):
        if self.public_web_url and self.environment == "production":
            from urllib.parse import urlsplit
            callback = urlsplit(self.google_redirect_uri)
            if not self.public_web_url.startswith("https://") or self.public_web_url.rstrip("/") != f"{callback.scheme}://{callback.netloc}":
                raise ValueError("PUBLIC_WEB_URL must be the HTTPS origin of GOOGLE_REDIRECT_URI.")
        if not (self.openrouter_api_key and self.openrouter_model):
            raise ValueError("OpenRouter requires OPENROUTER_API_KEY and OPENROUTER_MODEL.")
        if self.storage_provider == "supabase" and not (self.supabase_url.startswith("https://") and self.supabase_service_role_key and self.supabase_storage_bucket):
            raise ValueError("Supabase storage requires HTTPS SUPABASE_URL, service-role key and bucket.")
        return self

    @property
    def ai_model(self) -> str:
        return self.openrouter_model

    @property
    def ai_provider(self) -> str:
        """Compatibility alias retained in existing API responses."""
        return "openrouter"

    environment: Literal["development", "production"] = "development"
    cookie_secure: bool = False
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    login_attempts_per_minute: int = 20
    admin_email: str = "seyamesh91@gmail.com"
    google_client_id: str = Field(default_factory=lambda: _root_oauth("GOOGLE_CLIENT_ID", "Client_ID"),
                                  validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "Client_ID"))
    google_client_secret: str = Field(default_factory=lambda: _root_oauth("GOOGLE_CLIENT_SECRET", "Client_secret"),
                                      validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "Client_secret"))
    google_redirect_uri: str = Field(default_factory=lambda: _root_oauth("GOOGLE_REDIRECT_URI", default="http://localhost:5173/api/auth/google/callback"))

    @model_validator(mode="after")
    def production_settings(self):
        if self.environment == "production":
            if self.google_client_id and not self.google_redirect_uri.startswith("https://"):
                raise ValueError("Production GOOGLE_REDIRECT_URI must use HTTPS.")
            if len(self.secret_key) < 32:
                raise ValueError("Production SECRET_KEY must contain at least 32 characters.")
            if not self.cookie_secure:
                raise ValueError("Production requires COOKIE_SECURE=true and HTTPS.")
            origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
            if not origins or any(not o.startswith("https://") or "*" in o for o in origins):
                raise ValueError("Production CORS_ORIGINS must contain explicit HTTPS origins.")
            if "*" in self.allowed_hosts or not self.allowed_hosts.strip():
                raise ValueError("Production ALLOWED_HOSTS must contain explicit hostnames.")
        return self

    # Inline runs every job in the caller's thread (tests)
    job_queue_inline: bool = False

    secret_key: str = ""
    access_token_minutes: int = 480
    data_dir: str = "../data"
    pdf_render_dpi: int = 300
    ocr_max_side: int = 2560
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    min_label_confidence: float = 0.4

    @property
    def data_path(self) -> Path:
        if self.data_dir and self.data_dir != "../data":
            p = Path(self.data_dir).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p
        root_data = Path(__file__).resolve().parent.parent.parent / "data"
        if root_data.exists():
            return root_data
        p = Path(self.data_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def jwt_secret(self) -> str:
        if self.secret_key:
            return self.secret_key
        f = self.data_path / ".secret_key"
        if not f.exists():
            f.write_text(secrets.token_urlsafe(48))
        return f.read_text().strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ai_unavailable_message() -> str:
    return AI_UNAVAILABLE_MESSAGE


def ai_bad_response_message() -> str:
    return AI_BAD_RESPONSE_MESSAGE
