"""IndicOCR (Bodhan AI) for Indian-language subjects, via indic_ocr_service. No silent fallback to InternVL.

IndicOCR returns reading-ordered text blocks, not questions. Each block becomes one page-result item with the
question label taken from its text prefix; the segmentation services then merge continuation blocks as they do for InternVL.
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Type, TypeVar
import httpx
from pydantic import BaseModel
from ..config import INDIC_BAD_RESPONSE_MESSAGE, INDIC_UNAVAILABLE_MESSAGE, get_settings
from ..services import choices, tamil_blocks, tamil_format
from ..services.doc_structure import extract_section_marks_rule, is_document_header, is_section_heading_line
from ..services.numbering import extract_label_from_text_prefix
from .internvl import AICall
from .schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult

log = logging.getLogger("adem.indic")
T = TypeVar("T", bound=BaseModel)

# IndicOCR gives no recognition confidence (block `conf` is layout detection). Printed text reads reliably;
# handwriting is still "work in progress" upstream, so keep it below LOW_CONF and a teacher checks every answer.
_PRINTED_CONFIDENCE = 0.8
_HANDWRITING_CONFIDENCE = 0.5
# Not student or question content
# Block type/label (lower case, letters only): IndicOCR says "PageHeader", "Website-link", "Page-number", ...
_SKIP_KINDS = {"pageheader", "pagefooter", "header", "footer", "footnote", "websitelink", "dateline",
               "picture", "figure", "image", "chart", "seal", "advertisement"}
# Page numbers and paper codes; IndicOCR also files exam header lines ("[ மொத்த மதிப்பெண்கள் : 100") and mark rules
# ("3x8=24") under these, so those are kept
_FOLIO_KINDS = {"pagenumber", "folio", "number", "infobox"}
_ONLY_NUMBERS = re.compile(r"^[\d\s.\-–/]*$")
_REGISTER_BOX = re.compile(r"^\s*(?:(?:பதிவு|தேர்வு)?\s*எண்|Reg(?:ister|istration)?\.?\s*No\.?)?[\s\d]*$", re.I)


def _clean(text: str) -> str:
    """IndicOCR writes spaces as "▁" (runs of them for wide gaps) and sometimes wraps a handwritten number as math
    ("$$6)$$"): plain single spaces, no "$$", lines kept."""
    return "\n".join(re.sub(r"[ \t]{2,}", " ", line.replace("▁", " ").replace("$$", "")).strip()
                     for line in (text or "").splitlines()).strip()


def _kinds(block: dict) -> set[str]:
    return {re.sub(r"[^a-z]", "", str(block.get(k) or "").lower()) for k in ("type", "label")}


def _is_furniture(block: dict, text: str) -> bool:
    kinds = _kinds(block)
    if kinds & _SKIP_KINDS or _ONLY_NUMBERS.match(text):
        return True
    if "table" in kinds and _REGISTER_BOX.match(re.sub(r"<[^>]+>", " ", text)):  # the candidate's register-number box
        return True
    return bool(kinds & _FOLIO_KINDS) and not (is_document_header(text) or extract_section_marks_rule(text) is not None)


class IndicUnavailable(Exception):
    def __init__(self, detail: str = ""):
        super().__init__(INDIC_UNAVAILABLE_MESSAGE)
        self.detail = detail


class IndicResponseError(Exception):
    def __init__(self, kind: str, detail: str, raw: str = ""):
        super().__init__(INDIC_BAD_RESPONSE_MESSAGE)
        self.kind, self.detail, self.raw = kind, detail, raw


def uses_indic_ocr(subject_name: str | None) -> bool:
    """True when IndicOCR is enabled and the subject name matches INDIC_SUBJECTS (e.g. 'Tamil', 'Tamil II', 'தமிழ்')."""
    s = get_settings()
    if not s.indic_ocr_enabled or not subject_name:
        return False
    name = subject_name.casefold()
    return any(k.strip().casefold() in name for k in s.indic_subjects.split(",") if k.strip())


def text_model_for(subject_name: str | None) -> str | None:
    """Ollama model that grades this subject: INDIC_TEXT_MODEL for Indian-language subjects, else None (InternVL)."""
    model = get_settings().indic_text_model.strip()
    return model if model and uses_indic_ocr(subject_name) else None


def check_indic() -> dict:
    s = get_settings()
    try:
        r = httpx.get(f"{s.indic_ocr_url}/health", timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise IndicUnavailable(f"Cannot reach IndicOCR at {s.indic_ocr_url}: {e}") from e
    return {"available": True, "model": r.json().get("model"), "url": s.indic_ocr_url}


def release_indic() -> None:
    """Ask the IndicOCR service to free its GPU memory; it reloads on the next page."""
    s = get_settings()
    if not s.indic_ocr_enabled:
        return
    try:
        httpx.post(f"{s.indic_ocr_url}/release", timeout=30)
    except httpx.HTTPError as e:
        log.warning("Could not release IndicOCR GPU memory: %s", e)


def _parse_page(image_path: Path) -> dict:
    s = get_settings()
    try:
        with open(image_path, "rb") as f:
            r = httpx.post(f"{s.indic_ocr_url}/parse", files={"image": (Path(image_path).name, f)},
                           timeout=s.indic_ocr_timeout)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise IndicUnavailable(f"Cannot connect to IndicOCR: {e}") from e
    except httpx.TimeoutException as e:
        raise IndicResponseError("AI_ERROR", f"IndicOCR timed out: {e}") from e
    if r.status_code != 200:
        raise IndicResponseError("AI_ERROR", f"IndicOCR HTTP {r.status_code}: {r.text[:300]}", r.text)
    return r.json()


def _bbox(xyxy) -> dict | None:
    if not isinstance(xyxy, (list, tuple)) or len(xyxy) < 4:
        return None
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    return {"x": x0, "y": y0, "width": max(0.0, x1 - x0), "height": max(0.0, y1 - y0)}


def _merge_bbox(a: dict | None, b: dict | None) -> dict | None:
    if not a or not b:
        return a or b
    x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
    x1, y1 = max(a["x"] + a["width"], b["x"] + b["width"]), max(a["y"] + a["height"], b["y"] + b["height"])
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _group_answers(items: list[dict]) -> list[dict]:
    """IndicOCR splits one handwritten answer into paragraph blocks; InternVL returns it whole. Join each unlabelled
    block to the labelled answer above it. Unlabelled blocks at the top of the page stay separate so segmentation
    can carry them over to the previous page's last answer."""
    out: list[dict] = []
    for it in items:
        if it["question_number"] is None and out and out[-1]["question_number"] is not None:
            out[-1]["answer_text"] = f"{out[-1]['answer_text']}\n{it['answer_text']}"
            out[-1]["bbox"] = _merge_bbox(out[-1]["bbox"], it["bbox"])
        else:
            out.append(it)
    return out


_OPTION_BLOCK = re.compile(r"^\s*\(?\s*(?:[அஆஇஈ]|[a-dA-D])\s*[\)\.]")


# A question starts a line with its number: "41. ...", "7) ..." (not "(2)" or "(ii)" inside a note, not "3.00 மணி")
_QUESTION_START = re.compile(r"^\s*\d{1,3}\s*[.)](?!\d)")


def _split_headings(text: str) -> list[str]:
    """Cut a block at section heading lines ("பகுதி – அ"), notes ("குறிப்பு : ...") and question-number lines, so a
    heading or its instruction ("... 10 × 1 = 10") never fuses with a question and the section title stays just the
    heading. Sub-parts and options ("(அ)", "(ii)") stay inside their question."""
    parts: list[list[str]] = [[]]
    for line in text.splitlines():
        if is_section_heading_line(line):
            parts += [[line], []]
        elif parts[-1] and (_QUESTION_START.match(line) or tamil_format.starts_instruction(line)):
            parts.append([line])
        else:
            parts[-1].append(line)
    return [t for t in ("\n".join(p).strip() for p in parts) if t]


def _group_options(items: list[dict]) -> list[dict]:
    """A short "(அ) ..." / "(a) ..." block on its own is an MCQ option of the question above, not a new question.
    An either/or line ("அல்லது", "OR") and the alternative after it also belong to the question above."""
    out: list[dict] = []
    after_either_or = False
    for it in items:
        src = it.pop("_src")
        either_or = choices.is_either_or_line(src)
        if out and (either_or or after_either_or or (_OPTION_BLOCK.match(src) and len(src) < 120)):
            out[-1]["question_text"] = f"{out[-1]['question_text']}\n{src}"
            out[-1]["bbox"] = _merge_bbox(out[-1]["bbox"], it["bbox"])
        else:
            out.append(it)
        after_either_or = either_or
    return out


def blocks_to_result(page: dict, schema: Type[T], page_number: int) -> T:
    """Map IndicOCR blocks onto the same page-result schema InternVL fills."""
    blocks = sorted(page.get("blocks") or [], key=lambda b: b.get("order", 0))
    items = []
    for b in blocks:
        text = tamil_format.strip_page_furniture(_clean(b.get("text")))
        if not text or _is_furniture(b, text):
            continue
        bbox = _bbox(b.get("bbox_xyxy"))
        if issubclass(schema, QuestionPageResult):
            for seg in _split_headings(text):
                lbl, rest = extract_label_from_text_prefix(seg)
                items.append({"raw_question_number": lbl, "question_text": rest, "confidence": _PRINTED_CONFIDENCE,
                              "bbox": bbox, "_src": seg})
            continue
        lbl, rest = extract_label_from_text_prefix(text)
        if issubclass(schema, StudentPageResult) and lbl is None and _is_identity_block(text):
            continue  # the student's name and roll no. in the sheet header, not an answer
        if issubclass(schema, AnswerKeyPageResult):
            items.append({"question_number": lbl, "answer_text": rest, "confidence": _PRINTED_CONFIDENCE, "bbox": bbox})
        elif issubclass(schema, StudentPageResult):
            items.append({"question_number": lbl, "raw_question_label": lbl, "answer_text": rest, "bbox": bbox,
                          "mapping_status": "UNMAPPED", "ocr_confidence": _HANDWRITING_CONFIDENCE, "page_number": page_number})
        else:
            raise TypeError(f"IndicOCR cannot fill {schema.__name__}")
    if issubclass(schema, StudentPageResult):
        items = _group_answers(tamil_blocks.join_lone_numbers(items))
    elif issubclass(schema, QuestionPageResult):
        items = _group_options(items)
    key = "questions" if issubclass(schema, QuestionPageResult) else "answers"
    return schema.model_validate({"page_number": page_number, key: items})


# Answer-sheet header labels, English or Tamil. Roll before registration: "தேர்வு எண்" (exam no.) is the roll number.
_IDENTITY_LABELS = {
    "name": r"(?<![a-z])name\b|பெயர்",
    "roll_number": r"(?<![a-z])roll\s*(?:no|number)?\.?|வரிசை\s*எண்|தேர்வு\s*எண்|சுட்டெண்",
    # handwritten "Reg.No" is often read as "Key.NO" / "Rey No"; those only count with the "No" after them
    "registration_number": r"(?<![a-z])(?:reg(?:istration|ister|n)?\.?\s*(?:no|number)?|[kr]e[yq]\.?\s*no\b)\.?|பதிவு\s*எண்",
    "class_name": r"(?<![a-z])(?:class|std|standard)\b\.?|வகுப்பு",
    "section": r"(?<![a-z])sec(?:tion)?\b\.?|பிரிவு",
}
_IDENTITY_LABEL = re.compile("|".join(f"(?P<{k}>{v})" for k, v in _IDENTITY_LABELS.items()), re.I)


def parse_identity(text: str) -> dict:
    """Student details from header text: each value runs from its label to the next label or the line end."""
    out: dict = dict.fromkeys(_IDENTITY_LABELS)
    for line in (text or "").splitlines():
        found = list(_IDENTITY_LABEL.finditer(line))
        for i, m in enumerate(found):
            end = found[i + 1].start() if i + 1 < len(found) else len(line)
            value = line[m.end():end].strip(" \t:.-–|_")
            if value and out[m.lastgroup] is None:
                out[m.lastgroup] = value
    return out


def _is_identity_block(text: str) -> bool:
    """A short block giving the student's name and a roll/registration number."""
    read = parse_identity(text)
    return len(text.splitlines()) <= 6 and bool(read["name"]) and bool(read["roll_number"] or read["registration_number"])


LEGIBLE_LINES = 3  # this many lines of text read upright: the page is not photographed sideways


def read_identity(image_path: Path) -> dict:
    """parse_identity() of the page, plus "legible": whether it read as ordinary upright text."""
    page = _parse_page(Path(image_path))
    blocks = sorted(page.get("blocks") or [], key=lambda b: b.get("order", 0))
    text = "\n".join(_clean(b.get("text")) for b in blocks)
    return {**parse_identity(text), "legible": sum(1 for line in text.splitlines() if len(line) >= 10) >= LEGIBLE_LINES}


def read_page(image_path: Path, schema: Type[T], page_number: int) -> AICall:
    page = _parse_page(Path(image_path))
    raw = json.dumps(page, ensure_ascii=False)
    try:
        parsed = blocks_to_result(page, schema, page_number)
    except Exception as e:
        raise IndicResponseError("FAILED_PARSE", f"Unusable IndicOCR output: {e}", raw) from e
    if not any(getattr(parsed, k, None) for k in ("questions", "answers")):
        raise IndicResponseError("FAILED_PARSE", "IndicOCR found no text on this page", raw)
    return AICall(parsed, raw, 1)
