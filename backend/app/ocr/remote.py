"""OpenAI-compatible vision/text transport for OpenRouter and future private VLMs."""
from __future__ import annotations
import base64
import mimetypes
from pathlib import Path
import httpx
from ..config import get_settings


def connection():
    s = get_settings()
    if s.ai_provider == "openrouter":
        return "https://openrouter.ai/api/v1", s.openrouter_api_key, s.openrouter_model
    return s.custom_ai_base_url.rstrip("/"), s.custom_ai_api_key, s.custom_ai_model


def call(system: str, user: str, image: Path | None, structured: bool, model: str | None = None):
    s = get_settings()
    base, key, selected = connection()
    content: str | list = user
    if image:
        mime = mimetypes.guess_type(image.name)[0] or "image/png"
        content = [{"type": "text", "text": user}, {"type": "image_url", "image_url": {
            "url": f"data:{mime};base64," + base64.b64encode(image.read_bytes()).decode()}}]
    payload = {"model": model or selected, "messages": [{"role": "system", "content": system},
               {"role": "user", "content": content}], "stream": False, "temperature": 0,
               "max_tokens": s.internvl_num_predict}
    if structured:
        payload["response_format"] = {"type": "json_object"}
    if s.ai_request_logprobs:
        payload["logprobs"] = True
    headers = {"Authorization": "Bearer " + key}
    if s.public_web_url:
        headers["HTTP-Referer"] = s.public_web_url
        headers["X-Title"] = "Eval AI"
    response = httpx.post(base + "/chat/completions", json=payload, headers=headers, timeout=s.internvl_timeout)
    # Do not propagate provider response bodies or request headers into application logs.
    if not response.is_success:
        raise httpx.HTTPStatusError(f"AI provider returned HTTP {response.status_code}", request=response.request, response=response)
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("AI provider did not return a completion")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise ValueError("AI response exceeded its token limit; split the page or increase the configured limit")
    text = (choice.get("message") or {}).get("content") or ""
    if not isinstance(text, str):
        raise ValueError("AI provider returned unsupported content")
    return text, (choice.get("logprobs") or {}).get("content")


def status():
    s = get_settings()
    base, key, model = connection()
    if s.ai_provider == "openrouter":
        authentication = httpx.get(base + "/key", headers={"Authorization": "Bearer " + key}, timeout=15)
        if not authentication.is_success:
            raise RuntimeError("The OpenRouter API key could not be authenticated")
    response = httpx.get(base + "/models", headers={"Authorization": "Bearer " + key}, timeout=15)
    if not response.is_success:
        raise RuntimeError(f"AI provider health request failed (HTTP {response.status_code})")
    models = response.json().get("data") or []
    found = next((m for m in models if m.get("id") == model), None)
    if not found:
        raise RuntimeError("The configured AI model is not available from this provider")
    inputs = (found.get("architecture") or {}).get("input_modalities")
    if inputs is not None and "image" not in inputs:
        raise RuntimeError("The selected model does not accept images; choose a vision model")
    return {"available": True, "model": model, "provider": s.ai_provider, "url": base}
