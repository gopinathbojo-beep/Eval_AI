"""InternVL vision/text transport (Ollama on the remote model server) used for every AI task."""
from __future__ import annotations
import base64
import logging
from pathlib import Path
import httpx
from ..config import get_settings

log = logging.getLogger("adem.ai")


class CompletionLimitError(ValueError):
    def __init__(self, raw: str, completion_tokens=None, reasoning_tokens=None):
        super().__init__(
            "AI response exceeded its token limit; "
            f"completion_tokens={completion_tokens}, reasoning_tokens={reasoning_tokens}, "
            f"visible_characters={len(raw)}."
        )
        self.raw = raw


def connection():
    s = get_settings()
    return s.internvl_api_url.rstrip("/"), "", s.internvl_model


def call(system: str, user: str, image: Path | None, structured: bool, model: str | None = None):
    s = get_settings()
    base, _, selected = connection()
    message = {"role": "user", "content": user}
    if image:
        message["images"] = [base64.b64encode(image.read_bytes()).decode()]
    payload = {"model": model or selected, "messages": [{"role": "system", "content": system}, message],
               "stream": False, "options": {"temperature": 0, "num_ctx": s.internvl_num_ctx,
                                            "num_predict": s.ai_max_output_tokens}}
    if structured:
        payload["format"] = "json"
    if s.ai_request_logprobs:
        payload["logprobs"] = True
    response = httpx.post(base + "/api/chat", json=payload, timeout=s.internvl_timeout)
    if not response.is_success:
        raise httpx.HTTPStatusError(f"AI provider returned HTTP {response.status_code}", request=response.request, response=response)
    body = response.json()
    text = (body.get("message") or {}).get("content") or ""
    if not isinstance(text, str):
        raise ValueError("AI provider returned unsupported content")
    completion_tokens = body.get("eval_count")
    log.info("AI completion model=%s finish=%s completion_tokens=%s visible_characters=%d",
             model or selected, body.get("done_reason"), completion_tokens, len(text))
    if body.get("done_reason") == "length":
        raise CompletionLimitError(text, completion_tokens)
    probabilities = body.get("logprobs")  # same per-token shape as OpenAI's: token, logprob, bytes
    return text, probabilities or None


def status():
    base, _, model = connection()
    response = httpx.get(base + "/api/tags", timeout=15)
    if not response.is_success:
        raise RuntimeError(f"AI provider health request failed (HTTP {response.status_code})")
    names = {m.get("name") for m in response.json().get("models") or []} | {m.get("model") for m in response.json().get("models") or []}
    if model not in names and f"{model}:latest" not in names:
        raise RuntimeError("The configured InternVL model is not pulled on the model server")
    return {"available": True, "model": model, "provider": "internvl", "url": base}
