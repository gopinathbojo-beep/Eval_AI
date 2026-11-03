"""Structured Gemini extraction and grading through OpenRouter.

The module name remains as an internal compatibility shim for existing imports.
"""
from __future__ import annotations
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Type, TypeVar
import httpx
from pydantic import BaseModel, ValidationError
from ..config import get_settings, ai_unavailable_message, ai_bad_response_message
from . import confidence
from .parser import ParseError, extract_json_object

log = logging.getLogger("adem.ai")
T = TypeVar("T", bound=BaseModel)


class AIUnavailable(Exception):
    """OpenRouter is unreachable or the configured Gemini model is unavailable."""
    def __init__(self, detail: str = ""):
        super().__init__(ai_unavailable_message())
        self.detail = detail


class AIResponseError(Exception):
    """Model answered but not with usable structured output. `kind` is FAILED_PARSE or AI_ERROR."""
    def __init__(self, kind: str, detail: str, raw: str = ""):
        super().__init__(ai_bad_response_message())
        self.kind, self.detail, self.raw = kind, detail, raw


@dataclass
class AICall:
    parsed: BaseModel
    raw: str
    attempts: int


def check_model(model: str | None = None) -> dict:
    """Raise AIUnavailable unless OpenRouter exposes the configured vision model."""
    from .remote import status
    try:
        result = status()
        if model and model != result["model"]:
            raise RuntimeError("Only the configured OpenRouter model may be used")
        return result
    except (httpx.HTTPError, ValueError, RuntimeError):
        raise AIUnavailable("OpenRouter or its configured Gemini vision model is unavailable.") from None


def _call_once(system: str, user: str, image_path: Path | None, format: str | None = "json",
               model: str | None = None) -> str:
    from .remote import call
    try:
        raw, probabilities = call(system, user, Path(image_path) if image_path else None, bool(format), model)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise AIUnavailable("Cannot connect to OpenRouter.") from None
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 429:
            raise AIUnavailable("OpenRouter is rate limited. Retry later; no automatic repeated calls were made.") from None
        if error.response.status_code in {401, 402, 403}:
            raise AIUnavailable("OpenRouter rejected access. Check the API key, model access and available credits.") from None
        raise
    except ValueError as error:
        raise AIResponseError("FAILED_PARSE", str(error), getattr(error, "raw", "")) from None
    _last.logprobs = probabilities
    return raw


_last = threading.local()  # the token log-probabilities of this thread's last reply


def _measured(parsed: T, raw: str) -> T:
    """The page's items with the confidence measured from the reply just received, not the one the model wrote."""
    confidence.apply(parsed, raw, getattr(_last, "logprobs", None))
    if not getattr(_last, "logprobs", None):
        # Do not represent the model's self-reported number as measured OCR confidence.
        # Conservative values require human review when the provider supplies no token probabilities.
        for name in ("questions", "answers"):
            for item in getattr(parsed, name, []) or []:
                if hasattr(item, "ocr_confidence"):
                    item.ocr_confidence = min(item.ocr_confidence or 0.5, 0.5)
                elif hasattr(item, "confidence"):
                    item.confidence = min(item.confidence or 0.5, 0.5)
    return parsed


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


# The same few characters over and over at the end of a reply: the model is stuck in a loop (it reached its token
# limit repeating text it cannot read, e.g. a Hindi passage in an English paper)
_LOOP = re.compile(r"(.{4,200}?)\1{5,}", re.DOTALL)
LOOP_HINT = ("\n\nIMPORTANT: your previous reply for this page repeated the same text until it was cut off. If a passage is "
             "in a script you cannot read reliably (e.g. Hindi), do not transcribe it: write [Hindi passage] (or the "
             "language's name) in its place, and transcribe everything else on the page.")


def is_looping(raw: str) -> bool:
    """A repeated unit with letters in it: dotted blanks ("..........") are not a loop."""
    return any(sum(c.isalnum() for c in m.group(1)) >= 3 for m in _LOOP.finditer((raw or "")[-4000:]))


def _split_page_call(system: str, user: str, schema: Type[T], image_path: Path,
                     model: str | None = None, depth: int = 0) -> AICall:
    """Extract an over-limit page in two overlapping regions and merge its items."""
    import cv2

    image = cv2.imread(str(image_path))
    if image is None or image.shape[0] < 400:
        raise ValueError("The page image could not be split for extraction")
    height = image.shape[0]
    overlap = max(40, int(height * 0.04))
    middle = height // 2
    regions = [("TOP", 0, min(height, middle + overlap)),
               ("BOTTOM", max(0, middle - overlap), height)]
    parsed_regions: list[T] = []
    raw_regions: list[str] = []
    paths: list[Path] = []
    attempts = 0
    try:
        for label, start, end in regions:
            path = image_path.parent / f"{image_path.stem}_{label.lower()}_split{image_path.suffix}"
            paths.append(path)
            if not cv2.imwrite(str(path), image[start:end, :]):
                raise ValueError(f"Could not create the {label.lower()} page region")
            region_prompt = (
                re.sub(r"<source_text>.*?</source_text>",
                       "<source_text>Use only the visible cropped image.</source_text>",
                       user, flags=re.DOTALL)
                + f"\n\nTOKEN-LIMIT RECOVERY: This image is only the {label} region of the page. "
                  "Extract every visible item in this region. Do not invent content outside it. "
                  "Use coordinates relative to this cropped image. Keep JSON compact; do not repeat "
                  "full question text in tree context nodes. Preserve all visible wording once."
            )
            attempts += 1
            try:
                raw = _call_once(system, region_prompt, path, format="json", model=model)
                parsed = _measured(schema.model_validate(extract_json_object(raw)), raw)
            except AIResponseError as error:
                if "token limit" not in error.detail.lower() or depth >= 1:
                    raise
                recovered = _split_page_call(system, region_prompt, schema, path, model, depth + 1)
                parsed, raw = recovered.parsed, recovered.raw
                attempts += recovered.attempts
            for collection in ("questions", "answers", "fragments"):
                for item in getattr(parsed, collection, []) or []:
                    bbox = getattr(item, "bbox", None)
                    if isinstance(bbox, dict):
                        bbox["y"] = float(bbox.get("y", 0)) + start
                    elif bbox is not None:
                        bbox.y += start
                    for visual in getattr(item, "visuals", []) or []:
                        visual_bbox = getattr(visual, "bbox", None)
                        if isinstance(visual_bbox, dict):
                            visual_bbox["y"] = float(visual_bbox.get("y", 0)) + start
            parsed_regions.append(parsed)
            raw_regions.append(raw)
    finally:
        for path in paths:
            path.unlink(missing_ok=True)

    merged = parsed_regions[0].model_copy(deep=True)
    collection = next(
        (name for name in ("questions", "answers", "fragments") if hasattr(merged, name)),
        None,
    )
    if collection is None:
        raise ValueError("This extraction result cannot be merged after splitting")
    items = list(getattr(merged, collection) or [])
    seen = {
        (getattr(item, "raw_question_number", None) or getattr(item, "question_number", None)
         or getattr(item, "root", None),
         (getattr(item, "question_text", None) or getattr(item, "answer_text", None)
          or getattr(item, "text", None) or "").strip())
        for item in items
    }
    for item in getattr(parsed_regions[1], collection) or []:
        signature = (
            getattr(item, "raw_question_number", None) or getattr(item, "question_number", None)
            or getattr(item, "root", None),
            (getattr(item, "question_text", None) or getattr(item, "answer_text", None)
             or getattr(item, "text", None) or "").strip(),
        )
        if signature not in seen:
            items.append(item)
            seen.add(signature)
    setattr(merged, collection, items)
    if hasattr(merged, "instructions"):
        merged.instructions = list(dict.fromkeys(
            list(getattr(parsed_regions[0], "instructions", []) or [])
            + list(getattr(parsed_regions[1], "instructions", []) or [])
        ))
    if hasattr(merged, "issues"):
        merged.issues = list(dict.fromkeys(
            list(getattr(parsed_regions[0], "issues", []) or [])
            + list(getattr(parsed_regions[1], "issues", []) or [])
        ))
    if hasattr(merged, "metadata"):
        metadata = dict(getattr(parsed_regions[0], "metadata", {}) or {})
        for key, value in (getattr(parsed_regions[1], "metadata", {}) or {}).items():
            if metadata.get(key) is None and value is not None:
                metadata[key] = value
        merged.metadata = metadata
    return AICall(merged, "\n\n--- SPLIT REGION ---\n\n".join(raw_regions), attempts)


def chat_structured(system: str, user: str, schema: Type[T], image_path: Path | None = None,
                    model: str | None = None) -> AICall:
    """Call Gemini, parse and validate the response, with image split recovery when needed."""
    s = get_settings()
    attempts = s.ai_max_retries + 1
    raw, last_err, kind = "", "", "AI_ERROR"
    for i in range(1, attempts + 1):
        if i > 1 and is_looping(raw) and LOOP_HINT not in user:
            user += LOOP_HINT  # the same prompt would loop the same way again (temperature 0)
        try:
            raw = _call_once(system, user, image_path, format="json", model=model)
        except AIUnavailable:
            raise
        except AIResponseError as e:
            raw = e.raw
            if image_path is not None and "token limit" in e.detail.lower():
                try:
                    log.info("AI output limit reached; retrying %s as two page regions", image_path)
                    return _split_page_call(system, user, schema, Path(image_path), model)
                except AIUnavailable:
                    raise
                except AIResponseError as split_error:
                    raw = split_error.raw or raw
                    last_err, kind = f"Split-page recovery failed: {split_error.detail}", split_error.kind
                    log.warning("Split-page recovery failed for %s: %s", image_path, last_err)
                    break
                except Exception as split_error:
                    last_err, kind = f"Split-page recovery failed: {split_error}", "FAILED_PARSE"
                    log.warning("Split-page recovery failed for %s: %s", image_path, split_error)
                    continue
            last_err, kind = e.detail, e.kind
            if "token limit" in e.detail.lower():
                break  # An identical text request cannot recover a truncated response.
            continue
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_err, kind = f"HTTP/timeout error: {e}", "AI_ERROR"
            log.warning("InternVL attempt %d/%d failed: %s", i, attempts, last_err)
            continue
        try:
            obj = extract_json_object(raw)
            parsed = _measured(schema.model_validate(obj), raw)
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
                                    bot_raw = _call_once(system, user, bot_path, format="json", model=model)
                                    bot_obj = extract_json_object(bot_raw)
                                    bot_parsed = _measured(schema.model_validate(bot_obj), bot_raw)
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
                raw_clahe = _call_once(system, user, enhanced_img, format="json", model=model)
                obj_clahe = extract_json_object(raw_clahe)
                parsed_clahe = _measured(schema.model_validate(obj_clahe), raw_clahe)
                return AICall(parsed_clahe, raw_clahe, attempts + 1)
            except Exception:
                pass

            # Fallback to plain text transcription if JSON grammar constraint causes failures
            plain_user = user + "\n\nCRITICAL: Transcribe all visible questions and answers in Markdown with labels (e.g. Q1, Q2, 1>, 2>)."
            raw_plain = _call_once(system, plain_user, enhanced_img, format=None, model=model)
            fallback_parsed = fallback_parse_plain_text(raw_plain, schema)
            if fallback_parsed is not None:
                log.info("Successfully recovered page structure using plain text fallback.")
                return AICall(fallback_parsed, raw_plain, attempts + 2)
        except Exception as e:
            log.warning("2-stage fallback failed: %s", e)

    raise AIResponseError(kind, last_err, raw)
