from __future__ import annotations
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

AI_UNAVAILABLE_MESSAGE = (
    "InternVL3.5 4B is not available. Start Ollama and ensure "
    "blaifa/InternVL3_5:4B is installed."
)
AI_BAD_RESPONSE_MESSAGE = "InternVL3.5 4B failed to return a valid structured response."


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internvl_enabled: bool = True
    internvl_model: str = "blaifa/InternVL3_5:4B"
    internvl_api_url: str = "http://127.0.0.1:11434"
    internvl_timeout: int = 300
    internvl_max_retries: int = 2
    internvl_num_ctx: int = 8192
    internvl_num_predict: int = 4096

    # DB_MODE=local uses SQLite at data_path/adem.db; DB_MODE=supabase uses DATABASE_URL (Supabase/Postgres).
    db_mode: Literal["local", "supabase"] = "local"
    database_url: str = ""
    secret_key: str = ""
    access_token_minutes: int = 480
    data_dir: str = "../data"
    pdf_render_dpi: int = 300
    ocr_max_side: int = 2560
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
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
