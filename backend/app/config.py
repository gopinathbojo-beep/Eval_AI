from __future__ import annotations
import secrets
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

AI_UNAVAILABLE_MESSAGE = (
    "InternVL3.5 4B is not available. Start Ollama and ensure "
    "blaifa/InternVL3_5:4B is installed."
)
AI_BAD_RESPONSE_MESSAGE = "InternVL3.5 4B failed to return a valid structured response."
INDIC_UNAVAILABLE_MESSAGE = (
    "IndicOCR is not available. Start the IndicOCR service "
    "and check INDIC_OCR_URL."
)
INDIC_BAD_RESPONSE_MESSAGE = "IndicOCR failed to read this page."


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internvl_enabled: bool = True
    internvl_model: str = "blaifa/InternVL3_5:4B"
    internvl_api_url: str = "http://127.0.0.1:11434"
    internvl_timeout: int = 300
    internvl_max_retries: int = 2
    internvl_num_ctx: int = 8192
    internvl_num_predict: int = 4096

    # Indian-language subjects are read by IndicOCR instead of InternVL (separate IndicOCR service)
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

    # Empty = SQLite in the data dir. Postgres: postgresql+psycopg://user:password@host:5432/dbname
    database_url: str = ""
    secret_key: str = ""
    access_token_minutes: int = 480
    data_dir: str = "data"
    pdf_render_dpi: int = 300
    ocr_max_side: int = 2560
    max_upload_mb: int = 50
    # Web (school + teacher) :5173, Admin :5174, Parents :5175
    cors_origins: str = ("http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,"
                         "http://localhost:5175,http://127.0.0.1:5175")
    min_label_confidence: float = 0.4

    # Links in emails (invites, resets, signup checks) open these apps
    web_url: str = "http://localhost:5173"
    admin_url: str = "http://localhost:5174"
    parent_url: str = "http://localhost:5175"
    # Email. Without SMTP_HOST, emails are written to data/outbox/ instead of being sent (development).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "ADEM <noreply@localhost>"
    smtp_starttls: bool = True
    # Google sign-in: the OAuth Client ID. Empty = Google sign-in is switched off.
    google_client_id: str = ""
    # Supabase project. The secret key is server-only and must never reach a frontend.
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_jwks_url: str = ""
    # Sign-in protection
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    # Policy versions recorded with each consent
    privacy_version: str = "2026-10"
    terms_version: str = "2026-10"

    @property
    def data_path(self) -> Path:
        # a relative DATA_DIR is taken from the backend folder, not from wherever the server was started
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[1] / p
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
