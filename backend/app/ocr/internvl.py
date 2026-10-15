"""InternVL3.5 4B through Ollama's NATIVE /api/chat. No other model, no mock mode, no silent fallback."""
from __future__ import annotations
import base64
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Type, TypeVar
import httpx
from pydantic import BaseModel, ValidationError
from ..config import AI_BAD_RESPONSE_MESSAGE, AI_UNAVAILABLE_MESSAGE, get_settings
from .parser import ParseError, extract_json_object, salvage_truncated_object

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


class Cancelled(Exception):
    """The caller asked to stop (teacher pressed Cancel) while a model call was running."""


StopCheck = Callable[[], bool]
_POLL_SECONDS = 1.0


def _post(url: str, payload: dict, timeout: float, should_stop: StopCheck | None) -> httpx.Response:
    """POST that can be abandoned. The request runs on a worker thread while this thread polls `should_stop`;
    on stop the client is closed, which drops the connection so Ollama stops generating for it."""
    if should_stop is None:
        return httpx.post(url, json=payload, timeout=timeout)
    client = httpx.Client(timeout=timeout)
    box: dict = {}

    def work():
        try:
            box["r"] = client.post(url, json=payload)
        except BaseException as e:  # noqa: BLE001 - handed back to the calling thread
            box["e"] = e

    t = threading.Thread(target=work, daemon=True, name="ollama-call")
    t.start()
    try:
        while t.is_alive():
            t.join(_POLL_SECONDS)
            if t.is_alive() and should_stop():
                raise Cancelled()
    finally:
        client.close()
    if "e" in box:
        raise box["e"]
    return box["r"]


@dataclass
class AICall:
    parsed: BaseModel
    raw: str
    attempts: int
    dropped_items: int = 0   # malformed list entries left out to keep the rest of the page


def _drop_malformed_items(obj):
    """Keep the well-formed entries of item lists (e.g. "questions") when the model garbled one of them.
    Returns (cleaned object, number of entries dropped)."""
    def clean(lst):
        if not isinstance(lst, list) or not any(isinstance(x, dict) for x in lst):
            return lst, 0
        kept = [x for x in lst if isinstance(x, dict)]
        return kept, len(lst) - len(kept)
    if isinstance(obj, list):
        return clean(obj)
    if isinstance(obj, dict):
        out, dropped = dict(obj), 0
        for k, v in obj.items():
            out[k], n = clean(v)
            dropped += n
        return out, dropped
    return obj, 0


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


class _Truncated(Exception):
    """Model hit the output-token limit; the JSON is cut off and parts of the page would be lost."""
    def __init__(self, raw: str):
        super().__init__("output truncated")
        self.raw = raw


def _call_once(system: str, user: str, image_path: Path | None, temperature: float = 0.0,
               num_predict: int | None = None, seed: int | None = None, should_stop: StopCheck | None = None) -> str:
    s = get_settings()
    msg: dict = {"role": "user", "content": user}
    if image_path is not None:
        msg["images"] = [base64.b64encode(Path(image_path).read_bytes()).decode()]
    options = {"temperature": temperature, "num_ctx": s.internvl_num_ctx,
               "num_predict": num_predict or s.internvl_num_predict}
    if seed is not None:
        options["seed"] = seed
    payload = {
        "model": s.internvl_model,
        "stream": False,
        "format": "json",
        "options": options,
        "messages": [{"role": "system", "content": system}, msg],
    }
    try:
        r = _post(f"{s.internvl_api_url}/api/chat", payload, s.internvl_timeout, should_stop)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise AIUnavailable(f"Cannot connect to Ollama: {e}") from e
    if r.status_code == 404:
        raise AIUnavailable(f"Ollama 404 (model missing?): {r.text[:300]}")
    r.raise_for_status()
    body = r.json()
    content = (body.get("message") or {}).get("content", "") or ""
    prompt_tokens = body.get("prompt_eval_count")
    if prompt_tokens and prompt_tokens >= s.internvl_num_ctx * 0.95:
        log.warning("Prompt used %s of %s context tokens; Ollama may have dropped instructions. "
                    "Raise INTERNVL_NUM_CTX.", prompt_tokens, s.internvl_num_ctx)
    if body.get("done_reason") == "length":
        raise _Truncated(content)
    return content


_RETRY_HINT = ("\n\nIMPORTANT: your previous reply was not valid JSON for the required shape. "
               "Reply with ONLY the JSON object, all strings properly escaped, nothing before or after it.")


def chat_structured(system: str, user: str, schema: Type[T], image_path: Path | None = None,
                    should_stop: StopCheck | None = None) -> AICall:
    """Call the model, parse + validate against `schema`. Retries (max INTERNVL_MAX_RETRIES) on bad output/timeouts.

    Retries are not identical replays: at temperature 0 the same input yields the same broken output, so each
    retry varies the sampling slightly, and a truncated reply is retried with a larger output budget.
    `should_stop` is polled during each call and between retries; when it returns True, Cancelled is raised.
    """
    s = get_settings()
    attempts = s.internvl_max_retries + 1
    raw, last_err, kind = "", "", "AI_ERROR"
    num_predict = s.internvl_num_predict
    prompt = user
    partial: AICall | None = None   # best page salvaged by dropping malformed items, used only as a last resort
    for i in range(1, attempts + 1):
        temperature = 0.0 if i == 1 else 0.1 * (i - 1)
        if i > 1 and should_stop is not None and should_stop():
            raise Cancelled()
        try:
            raw = _call_once(system, prompt, image_path, temperature, num_predict, seed=None if i == 1 else 1000 + i,
                             should_stop=should_stop)
        except (AIUnavailable, Cancelled):
            raise
        except _Truncated as e:
            raw = e.raw
            last_err, kind = f"Output truncated at num_predict={num_predict}", "FAILED_PARSE"
            log.warning("InternVL attempt %d/%d: %s", i, attempts, last_err)
            num_predict = min(num_predict * 2, max(s.internvl_max_num_predict, num_predict))
            if i == attempts:
                salvaged = salvage_truncated_object(raw)
                if salvaged is not None:
                    try:
                        parsed = schema.model_validate(salvaged)
                        log.warning("Using salvaged prefix of truncated output (last item may be missing)")
                        return AICall(parsed, raw, i)
                    except ValidationError:
                        pass
            continue
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_err, kind = f"HTTP/timeout error: {e}", "AI_ERROR"
            log.warning("InternVL attempt %d/%d failed: %s", i, attempts, last_err)
            continue
        try:
            obj = extract_json_object(raw)
            return AICall(schema.model_validate(obj), raw, i)
        except ParseError as e:
            last_err, kind = f"JSON parse failed: {e}", "FAILED_PARSE"
        except ValidationError as e:
            last_err, kind = f"Schema validation failed: {e.errors()[:3]}", "FAILED_PARSE"
            cleaned, dropped = _drop_malformed_items(obj)
            if dropped:
                try:
                    cand = AICall(schema.model_validate(cleaned), raw, i, dropped)
                    if partial is None or dropped < partial.dropped_items:
                        partial = cand
                except ValidationError:
                    pass
        prompt = user + _RETRY_HINT
        log.warning("InternVL attempt %d/%d invalid output: %s | raw[:300]=%r", i, attempts, last_err, raw[:300])
    if partial is not None:
        log.warning("Using page with %d malformed item(s) dropped: %s", partial.dropped_items, last_err)
        return partial
    raise AIResponseError(kind, last_err, raw)
