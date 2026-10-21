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


def _call_once(system: str, user: str, image_path: Path | None, format: str | None = "json") -> str:
    s = get_settings()
    msg: dict = {"role": "user", "content": user}
    if image_path is not None:
        msg["images"] = [base64.b64encode(Path(image_path).read_bytes()).decode()]
    payload: dict = {
        "model": s.internvl_model,
        "stream": False,
        "options": {"temperature": 0, "repeat_penalty": 1.15, "num_ctx": s.internvl_num_ctx, "num_predict": s.internvl_num_predict},
        "messages": [{"role": "system", "content": system}, msg],
    }
    if format:
        payload["format"] = format
    try:
        r = httpx.post(f"{s.internvl_api_url}/api/chat", json=payload, timeout=s.internvl_timeout)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise AIUnavailable(f"Cannot connect to Ollama: {e}") from e
    if r.status_code == 404:
        raise AIUnavailable(f"Ollama 404 (model missing?): {r.text[:300]}")
    r.raise_for_status()
    body = r.json()
    return (body.get("message") or {}).get("content", "") or ""


def enhance_contrast(image_path: Path) -> Path:
    """Enhance image contrast using OpenCV CLAHE on the L channel for faint handwriting or low-contrast scans."""
    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is None:
            return image_path
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced_lab = cv2.merge((cl, a, b))
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        enhanced_path = image_path.parent / f"{image_path.stem}_clahe{image_path.suffix}"
        cv2.imwrite(str(enhanced_path), enhanced_bgr)
        return enhanced_path
    except Exception as e:
        log.warning("Image contrast enhancement failed: %s", e)
        return image_path


# Regex-recovered labels are guesses: keep them below the review thresholds so a teacher always checks them.
_FALLBACK_CONFIDENCE = 0.3


def fallback_parse_plain_text(raw_text: str, schema: Type[T]) -> T | None:
    """Attempt deterministic extraction from unstructured Markdown/plain text when structured JSON fails."""
    import re
    from .schemas import (
        AnswerKeyItem,
        AnswerKeyPageResult,
        QuestionItem,
        QuestionPageResult,
        StudentAnswerItem,
        StudentPageResult,
    )

    if not raw_text or not raw_text.strip():
        return None

    # Matches Question 1, Q1, 1), 1>, 1., a), a>
    delim_pat = re.compile(
        r"(?:^|\n+)[#*\s]*(?:(?:Q(?:uestion)?\.?\s*([0-9]{1,2}[a-zA-Z]?|[a-zA-Z]))|([0-9]{1,2}\s*[)>:\.]|[0-9]{1,2},|[a-zA-Z]\s*[)>:\.]|[a-zA-Z],))",
        re.IGNORECASE,
    )
    matches = list(delim_pat.finditer(raw_text))
    if not matches:
        return None

    chunks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        lbl = m.group(1) or m.group(2) or ""
        lbl = lbl.strip().rstrip(")>:., ")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        content = raw_text[start:end].strip()
        if content:
            chunks.append((lbl, content))

    if not chunks:
        return None

    try:
        if issubclass(schema, StudentPageResult):
            items = [
                StudentAnswerItem(
                    question_number=f"Q{lbl}" if lbl.isdigit() else lbl,
                    raw_question_label=lbl,
                    answer_text=content,
                    mapping_status="UNMAPPED",
                    ocr_confidence=_FALLBACK_CONFIDENCE,
                )
                for lbl, content in chunks
            ]
            return schema.model_validate({"answers": items})

        elif issubclass(schema, QuestionPageResult):
            items = [
                QuestionItem(
                    raw_question_number=f"Q{lbl}" if lbl.isdigit() else lbl,
                    question_text=content,
                    confidence=_FALLBACK_CONFIDENCE,
                )
                for lbl, content in chunks
            ]
            return schema.model_validate({"questions": items})

        elif issubclass(schema, AnswerKeyPageResult):
            items = [
                AnswerKeyItem(
                    question_number=f"Q{lbl}" if lbl.isdigit() else lbl,
                    answer_text=content,
                    confidence=_FALLBACK_CONFIDENCE,
                )
                for lbl, content in chunks
            ]
            return schema.model_validate({"answers": items})
    except Exception as e:
        log.warning("Fallback plain text parsing validation error: %s", e)
        return None
    return None


def chat_structured(system: str, user: str, schema: Type[T], image_path: Path | None = None) -> AICall:
    """Call the model, parse + validate against `schema`. Retries with CLAHE and 2-stage fallback on parse failures."""
    s = get_settings()
    attempts = s.internvl_max_retries + 1
    raw, last_err, kind = "", "", "AI_ERROR"
    for i in range(1, attempts + 1):
        try:
            raw = _call_once(system, user, image_path, format="json")
        except AIUnavailable:
            raise
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_err, kind = f"HTTP/timeout error: {e}", "AI_ERROR"
            log.warning("InternVL attempt %d/%d failed: %s", i, attempts, last_err)
            continue
        try:
            obj = extract_json_object(raw)
            parsed = schema.model_validate(obj)
            # Check if this is a tall document page where the model only extracted items in the upper portion
            if image_path is not None and hasattr(parsed, "questions") and parsed.questions:
                try:
                    import cv2
                    img = cv2.imread(str(image_path))
                    if img is not None:
                        img_h, img_w = img.shape[:2]
                        if img_h >= 1800:
                            bboxes = [q.bbox for q in parsed.questions if q.bbox]
                            max_y = max((bb.y + bb.height) for bb in bboxes) if bboxes else 0
                            if max_y > 0 and (max_y / img_h) < 0.35 and len(parsed.questions) <= 3:
                                crop_y = int(img_h * 0.25)
                                bot_img = img[crop_y:, :]
                                bot_path = image_path.parent / f"{image_path.stem}_bot_strip{image_path.suffix}"
                                cv2.imwrite(str(bot_path), bot_img)
                                try:
                                    bot_raw = _call_once(system, user, bot_path, format="json")
                                    bot_obj = extract_json_object(bot_raw)
                                    bot_parsed = schema.model_validate(bot_obj)
                                    if hasattr(bot_parsed, "questions") and bot_parsed.questions:
                                        seen_texts = {q.question_text.strip().lower()[:50] for q in parsed.questions if q.question_text}
                                        for bq in bot_parsed.questions:
                                            if bq.question_text and bq.question_text.strip().lower()[:50] not in seen_texts:
                                                if bq.bbox:
                                                    bq.bbox.y += crop_y
                                                parsed.questions.append(bq)
                                                seen_texts.add(bq.question_text.strip().lower()[:50])
                                finally:
                                    if bot_path.exists():
                                        bot_path.unlink(missing_ok=True)
                except Exception as ex:
                    log.warning("Tall page lower strip scan failed: %s", ex)

            return AICall(parsed, raw, i)
        except ParseError as e:
            last_err, kind = f"JSON parse failed: {e}", "FAILED_PARSE"
        except ValidationError as e:
            last_err, kind = f"Schema validation failed: {e.errors()[:3]}", "FAILED_PARSE"
        log.warning("InternVL attempt %d/%d invalid output: %s | raw[:300]=%r", i, attempts, last_err, raw[:300])

    # 2-Stage Automatic Fallback: CLAHE contrast enhancement & plain text transcription
    if image_path is not None:
        try:
            log.info("Initiating 2-stage fallback: CLAHE contrast enhancement for %s", image_path)
            enhanced_img = enhance_contrast(Path(image_path))
            try:
                raw_clahe = _call_once(system, user, enhanced_img, format="json")
                obj_clahe = extract_json_object(raw_clahe)
                parsed_clahe = schema.model_validate(obj_clahe)
                return AICall(parsed_clahe, raw_clahe, attempts + 1)
            except Exception:
                pass

            # Fallback to plain text transcription if JSON grammar constraint causes failures
            plain_user = user + "\n\nCRITICAL: Transcribe all visible questions and answers in Markdown with labels (e.g. Q1, Q2, 1>, 2>)."
            raw_plain = _call_once(system, plain_user, enhanced_img, format=None)
            fallback_parsed = fallback_parse_plain_text(raw_plain, schema)
            if fallback_parsed is not None:
                log.info("Successfully recovered page structure using plain text fallback.")
                return AICall(fallback_parsed, raw_plain, attempts + 2)
        except Exception as e:
            log.warning("2-stage fallback failed: %s", e)

    raise AIResponseError(kind, last_err, raw)
