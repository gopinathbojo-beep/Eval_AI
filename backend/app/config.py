from __future__ import annotations
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import AliasChoices, Field, model_validator
from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

AI_UNAVAILABLE_MESSAGE = (
    "InternVL3.5 4B is not available. Start Ollama and ensure "
    "blaifa/InternVL3_5:4B is installed."
)
AI_BAD_RESPONSE_MESSAGE = "InternVL3.5 4B failed to return a valid structured response."
INDIC_UNAVAILABLE_MESSAGE = (
    "IndicOCR is not available. Start the IndicOCR service (indic_ocr_service) "
    "and check INDIC_OCR_URL."
)
INDIC_BAD_RESPONSE_MESSAGE = "IndicOCR failed to read this page."


def _root_oauth(name: str, legacy: str = "", default: str = "") -> str:
    # Only OAuth settings are read from the root .env; existing backend settings retain their sources.
    path = Path(__file__).resolve().parents[2] / ".env"
    values = {k.lower(): v for k, v in dotenv_values(path).items() if v} if path.exists() else {}
    return values.get(name.lower(), values.get(legacy.lower(), default))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    internvl_enabled: bool = True
    internvl_model: str = "blaifa/InternVL3_5:4B"
    internvl_api_url: str = "http://127.0.0.1:11434"
    internvl_timeout: int = 300
    internvl_max_retries: int = 2
    internvl_num_ctx: int = 8192
    internvl_num_predict: int = 4096

    # Indian-language subjects are read by IndicOCR instead of InternVL (see indic_ocr_service/)
    indic_ocr_enabled: bool = False
    indic_ocr_url: str = "http://127.0.0.1:8090"
    indic_ocr_timeout: int = 300
    indic_subjects: str = ("tamil,தமிழ்,hindi,हिन्दी,telugu,kannada,malayalam,marathi,bengali,gujarati,"
                           "odia,punjabi,assamese,urdu,sanskrit")
    # Optional Ollama model that grades and labels those subjects. Empty = InternVL grades, AI labeler off.
    indic_text_model: str = ""

    # GPU jobs run on worker threads, up to this many at once per engine. Keep INTERNVL_PARALLEL_JOBS at or below
    # OLLAMA_NUM_PARALLEL on the Ollama machine, or Ollama just queues the extra requests.
    internvl_parallel_jobs: int = 1
    indic_parallel_jobs: int = 1
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
