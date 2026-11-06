"""OpenRouter transport: every AI task uses the one model named by OPENROUTER_MODEL."""
from __future__ import annotations
import base64
import mimetypes
import logging
import os
import ssl
from functools import lru_cache
from pathlib import Path
import certifi
import httpx
from ..config import get_settings

log = logging.getLogger("adem.ai")


@lru_cache(maxsize=1)
def tls_context():
    """Keep certificate verification, including trusted Windows-installed issuers.

    HTTPX's certifi-only default cannot see an organisation/antivirus certificate
    installed in Windows. Honour explicit certificate configuration first.
    """
    cafile, capath = os.environ.get("SSL_CERT_FILE"), os.environ.get("SSL_CERT_DIR")
    if cafile or capath:
        return ssl.create_default_context(cafile=cafile, capath=capath)
    context = ssl.create_default_context(cafile=certifi.where())
    if os.name == "nt":
        context.load_default_certs()
    return context


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
    return s.openrouter_base_url.rstrip("/"), s.openrouter_api_key, s.medium_model  # the default tier; small jobs pass get_settings().small_model


def _headers(key: str) -> dict:
    return {"Authorization": "Bearer " + key} if key else {}


def call(system: str, user: str, image: Path | None, structured: bool, model: str | None = None,
         _retry: bool = False):
    s = get_settings()
    base, key, selected = connection()
    content: str | list = user
    if image:
        mime = mimetypes.guess_type(image.name)[0] or "image/png"
        content = [{"type": "text", "text": user}, {"type": "image_url", "image_url": {
            "url": f"data:{mime};base64," + base64.b64encode(image.read_bytes()).decode()}}]
    payload = {"model": model or selected, "messages": [{"role": "system", "content": system},
               {"role": "user", "content": content}], "stream": False, "temperature": 0,
               "max_tokens": s.ai_max_output_tokens}
    if structured:
        payload["response_format"] = {"type": "json_object"}
    if s.ai_request_logprobs:
        payload["logprobs"] = True
    # thinking models otherwise spend the whole output budget reasoning about a page;
    # DeepSeek ignores effort "minimal" (all 8192 tokens on one page), so page reads turn thinking off
    payload["reasoning"] = ({"enabled": False} if _retry or (image and s.ai_ocr_reasoning_effort == "minimal")
                            else {"effort": s.ai_ocr_reasoning_effort if image else s.ai_text_reasoning_effort,
                                  "exclude": True})
    headers = _headers(key)
    if s.public_web_url:
        headers["HTTP-Referer"] = s.public_web_url
        headers["X-Title"] = "Eval AI"
    response = httpx.post(base + "/v1/chat/completions", json=payload, headers=headers, timeout=s.ai_timeout,
                          verify=tls_context())
    # Do not propagate provider response bodies or request headers into application logs.
    if not response.is_success:
        raise httpx.HTTPStatusError(f"AI provider returned HTTP {response.status_code}", request=response.request, response=response)
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("AI provider did not return a completion")
    choice = choices[0]
    text = (choice.get("message") or {}).get("content") or ""
    if not isinstance(text, str):
        raise ValueError("AI provider returned unsupported content")
    usage = body.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    log.info("AI completion model=%s finish=%s completion_tokens=%s reasoning_tokens=%s visible_characters=%d",
             model or selected, choice.get("finish_reason"), completion_tokens, reasoning_tokens, len(text))
    if choice.get("finish_reason") == "length":
        if not text.strip() and payload["reasoning"].get("enabled") is not False and not _retry:
            # the whole budget went on thinking and nothing came back (long sheets, long answers):
            # ask once more with thinking off, as page reads already do
            log.info("AI spent its output budget reasoning; asking again without reasoning")
            return call(system, user, image, structured, model, _retry=True)
        raise CompletionLimitError(text, completion_tokens, reasoning_tokens)
    return text, (choice.get("logprobs") or {}).get("content")


def status():
    base, key, model = connection()
    authentication = httpx.get(base + "/v1/key", headers=_headers(key), timeout=15, verify=tls_context())
    if not authentication.is_success:
        raise RuntimeError("The OpenRouter API key could not be authenticated")
    response = httpx.get(base + "/v1/models", headers=_headers(key), timeout=15, verify=tls_context())
    if not response.is_success:
        raise RuntimeError(f"AI provider health request failed (HTTP {response.status_code})")
    found = next((m for m in response.json().get("data") or [] if m.get("id") == model), None)
    if not found:
        raise RuntimeError("OPENROUTER_MODEL is not available on OpenRouter")
    inputs = (found.get("architecture") or {}).get("input_modalities")
    if inputs is not None and "image" not in inputs:
        raise RuntimeError("OPENROUTER_MODEL does not accept images; choose a vision model")
    return {"available": True, "model": model, "provider": "openrouter", "url": base}
