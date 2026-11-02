"""Legacy block-to-schema adapter retained for deterministic Tamil parser fixtures.

The production application no longer calls an IndicOCR service; Gemini reads every language through OpenRouter.
"""
from __future__ import annotations
import re
from typing import Type, TypeVar
from pydantic import BaseModel
from ..formatter.common import choices
from ..formatter.tamil import blocks as tamil_blocks
from ..formatter.tamil import format as tamil_format
from ..formatter.common.paper import extract_section_marks_rule, is_document_header, is_section_heading_line
from ..formatter.common.numbering import extract_label_from_text_prefix
from .schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult

T = TypeVar("T", bound=BaseModel)

# Legacy parser fixtures may contain `text_conf` (recognition certainty) and `conf`
# (layout-box certainty). Missing recognition confidence remains conservative for
# handwriting so a teacher reviews uncertain answers.
_PRINTED_CONFIDENCE = 0.8
_HANDWRITING_CONFIDENCE = 0.5


def _confidence(block: dict, fallback: float) -> float:
    measured = block.get("text_conf")
    return float(measured) if isinstance(measured, (int, float)) else fallback
# Not student or question content
# Block type/label (lower case, letters only) used by the legacy fixture adapter.
_SKIP_KINDS = {"pageheader", "pagefooter", "header", "footer", "footnote", "websitelink", "dateline",
               "picture", "figure", "image", "chart", "seal", "advertisement"}
# Page numbers and paper codes; IndicOCR also files exam header lines ("[ மொத்த மதிப்பெண்கள் : 100") and mark rules
# ("3x8=24") under these, so those are kept
_FOLIO_KINDS = {"pagenumber", "folio", "number", "infobox"}
_CONTENT_WORDS = 20  # a folio-kind block this long is text (page numbers and paper codes are a few words)
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
    if kinds & _FOLIO_KINDS and len(text.split()) >= _CONTENT_WORDS:
        return False  # a boxed model letter or passage the layout model calls an "Infobox": content, not a folio
    return bool(kinds & _FOLIO_KINDS) and not (is_document_header(text) or extract_section_marks_rule(text) is not None)


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
            a, b = (len(x["answer_text"].split()) or 1 for x in (out[-1], it))
            out[-1]["ocr_confidence"] = (out[-1]["ocr_confidence"] * a + it["ocr_confidence"] * b) / (a + b)  # per word
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
                items.append({"raw_question_number": lbl, "question_text": rest, "confidence": _confidence(b, _PRINTED_CONFIDENCE),
                              "bbox": bbox, "_src": seg})
            continue
        lbl, rest = extract_label_from_text_prefix(text)
        if issubclass(schema, StudentPageResult) and lbl is None and _is_identity_block(text):
            continue  # the student's name and roll no. in the sheet header, not an answer
        if issubclass(schema, AnswerKeyPageResult):
            items.append({"question_number": lbl, "answer_text": rest, "confidence": _confidence(b, _PRINTED_CONFIDENCE),
                          "bbox": bbox})
        elif issubclass(schema, StudentPageResult):
            items.append({"question_number": lbl, "raw_question_label": lbl, "answer_text": rest, "bbox": bbox,
                          "mapping_status": "UNMAPPED", "ocr_confidence": _confidence(b, _HANDWRITING_CONFIDENCE),
                          "page_number": page_number})
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
