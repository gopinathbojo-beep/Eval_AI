"""InternVL3.5 4B through Ollama's NATIVE /api/chat. No other model, no mock mode, no silent fallback."""
from __future__ import annotations
import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Type, TypeVar
import httpx
from pydantic import BaseModel, ValidationError
from ..config import AI_BAD_RESPONSE_MESSAGE, AI_UNAVAILABLE_MESSAGE, get_settings
from .parser import ParseError, extract_json_object

log = logging.getLogger("adem.ai")
T = TypeVar("T", bound=BaseModel)


class AIUnavailable(Exception):
    """Ollama unreachable, disabled, or the required model is not installed."""
    def __init__(self, detail: str = ""):
        super().__init__(AI_UNAVAILABLE_MESSAGE)
        self.detail = detail


class AIResponseError(Exception):
    """Model answered but not with usable structured output. `kind` is FAILED_PARSE or AI_ERROR."""
    def __init__(self, kind: str, detail: str, raw: str = ""):
        super().__init__(AI_BAD_RESPONSE_MESSAGE)
        self.kind, self.detail, self.raw = kind, detail, raw


@dataclass
class AICall:
    parsed: BaseModel
    raw: str
    attempts: int


def _same_model(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def check_model() -> dict:
    """Raises AIUnavailable unless Ollama is up AND the exact model is installed."""
    s = get_settings()
    if not s.internvl_enabled:
        raise AIUnavailable("INTERNVL_ENABLED is false")
    try:
        r = httpx.get(f"{s.internvl_api_url}/api/tags", timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise AIUnavailable(f"Cannot reach Ollama at {s.internvl_api_url}: {e}") from e
    names = [m.get("name", "") for m in r.json().get("models", [])] + \
            [m.get("model", "") for m in r.json().get("models", [])]
    if not any(_same_model(n, s.internvl_model) for n in names):
        raise AIUnavailable(f"Model {s.internvl_model} not found. Installed: {sorted(set(names))}")
    return {"available": True, "model": s.internvl_model, "url": s.internvl_api_url}


def _call_once(system: str, user: str, image_path: Path | None) -> str:
    s = get_settings()
    msg: dict = {"role": "user", "content": user}
    if image_path is not None:
        msg["images"] = [base64.b64encode(Path(image_path).read_bytes()).decode()]
    payload = {
        "model": s.internvl_model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "repeat_penalty": 1.15, "num_ctx": s.internvl_num_ctx, "num_predict": s.internvl_num_predict},
        "messages": [{"role": "system", "content": system}, msg],
    }
    try:
        r = httpx.post(f"{s.internvl_api_url}/api/chat", json=payload, timeout=s.internvl_timeout)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise AIUnavailable(f"Cannot connect to Ollama: {e}") from e
    if r.status_code == 404:
        raise AIUnavailable(f"Ollama 404 (model missing?): {r.text[:300]}")
    r.raise_for_status()
    body = r.json()
    return (body.get("message") or {}).get("content", "") or ""


def chat_structured(system: str, user: str, schema: Type[T], image_path: Path | None = None) -> AICall:
    """Call the model, parse + validate against `schema`. Retries (max INTERNVL_MAX_RETRIES) on bad output/timeouts."""
    s = get_settings()
    attempts = s.internvl_max_retries + 1
    raw, last_err, kind = "", "", "AI_ERROR"
    for i in range(1, attempts + 1):
        try:
            raw = _call_once(system, user, image_path)
        except AIUnavailable:
            raise
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_err, kind = f"HTTP/timeout error: {e}", "AI_ERROR"
            log.warning("InternVL attempt %d/%d failed: %s", i, attempts, last_err)
            continue
        try:
            obj = extract_json_object(raw)
            parsed = schema.model_validate(obj)
            # If answers were expected from an answer sheet image but 0 were parsed while raw mentions questions
            if hasattr(parsed, "answers") and len(parsed.answers) == 0 and ("question" in raw.lower() or "answer" in raw.lower()):
                raise ParseError("0 answers parsed from model output containing question text")
            return AICall(parsed, raw, i)
        except ParseError as e:
            last_err, kind = f"JSON parse failed: {e}", "FAILED_PARSE"
        except ValidationError as e:
            last_err, kind = f"Schema validation failed: {e.errors()[:3]}", "FAILED_PARSE"
        log.warning("InternVL attempt %d/%d invalid output: %s | raw[:300]=%r", i, attempts, last_err, raw[:300])
    raise AIResponseError(kind, last_err, raw)
