"""Question paper structure for Tamil subjects (paper_format.TAMIL), in place of the English structure parser.

A Tamil paper reads top to bottom as header -> பகுதி / பிரிவு (with its marks rule and notes) -> questions. A question
starts at its number ("வினா 1.", "1.", "வினா எண் 3 (அ)"); everything up to the next number belongs to it: sub-parts
அ) ஆ) இ), MCQ options, a poem or passage, blanks, its own குறிப்பு. So sub-parts stay inside their question, as the
key marks them ("வினா 2 ... அ) ... ஆ) ...").

Layouts it was built against:
  TN SSLC Tamil (8501, 2025): "1." numbers, (அ)-(ஈ) options, "4x2=8" notes, "எவையேனும் நான்கு", "அல்லது" choices
  Class 8 Tamil (school paper): "வினா 1." numbers, "(4 வினாக்கள் × 2 மதிப்பெண்கள் = 8 மதிப்பெண்கள்)" rules, marks as a
    bare "(2)" on the question or each part, a poem / passage inside the question, "மொத்தம்: 30 மதிப்பெண்கள்" footer

A question's marks, first found: its own mark ("வினா 5. ... (3)"); its parts' marks added up ("அ) ... (1)",
"ஆ) ... (1)"), the higher alternative of an either/or; the OCR's marks; the section rule ("4 × 2 = 8" -> 2).

Choices: "அல்லது" between alternatives makes one question per alternative sharing choice_group (choices.py);
"அல்லது" inside a sentence ("மூன்று அல்லது நான்கு வாக்கியங்களில்") is just a word. "Write on any one of these topics"
(ஏதேனும் ஒன்றைப் பற்றி ... அ) ஆ) இ)) stays one question: the student writes one answer and the key has one.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any

from . import choices, paper_format, tamil_format
from .tamil_blocks import split_key_blocks, split_question_blocks
from .doc_structure import (
    DocumentStructure, StructuredQuestion, _apply_answer_rules, _note_answer_rule, _split_choices,
    default_question_type, extract_exam_total_marks, is_document_header, is_instruction, is_section_heading_line,
    keyword_question_type,
)
from .numbering import normalize_question_number, parent_number, subpart_path

# A line opening a sub-part: "அ) ...", "(ஆ) ...", "(a) ...", "(ii) ..."
_PART_LINE = re.compile(rf"^\s*(?:•\s*)?(?:\(\s*(?:[{tamil_format.SUB_LETTERS}]|[a-h]|[ivx]{{1,4}})\s*\)|(?:[{tamil_format.SUB_LETTERS}]|[a-h])\s*\))")
_MAX_SKIP = 2  # a question number may jump this far past the last one (the OCR missed a question)
_PARTS = "BCDEFGH"


def _opens_section(item: Any) -> bool:
    """A section heading ("பகுதி – அ", "பிரிவு - 2") or a roman-numbered section line ("II. ... 5 × 2 = 10")."""
    text = (item.question_text or "").strip()
    label = (item.raw_question_number or "").strip()
    if not label:
        return is_section_heading_line(text.partition("\n")[0]) or tamil_format.is_roman_section(text)
    return bool(re.fullmatch(r"[IVX]{1,4}\.?", label)) and tamil_format.is_roman_section(f"{label}. {text}")


@dataclass
class _Q:
    num: int
    lines: list[str]
    section: str | None
    page_start: int
    page_end: int
    bbox: dict | None
    confidence: float | None
    qtype: str | None
    ocr_marks: float | None
    ocr_part_marks: list[float] = field(default_factory=list)
    part: str = ""  # "B", "C", ... for a section whose numbering restarts at 1


def _shown_part(token: str, text: str) -> str:
    """"(அ)" for part a of a Tamil question (the label the OCR took off), "(ii)" as it is."""
    if token in "abcdefgh" and len(token) == 1 and tamil_format.has_tamil(text):
        token = tamil_format.SUB_LETTERS["abcdefgh".index(token)]
    return f"({token})"


def _marks(q: _Q, rule: float | None) -> tuple[float | None, str | None]:
    """(marks, review reason) for one question, see the module docstring."""
    lines = [l for block in q.lines for l in block.splitlines() if l.strip()]
    first_part = next((i for i, l in enumerate(lines) if _PART_LINE.match(l)), None)
    head = lines if first_part is None else lines[:first_part]
    own = [m for l in head if (m := tamil_format.line_marks(l)) is not None]
    if own:
        return own[-1], None
    if q.ocr_marks:
        return q.ocr_marks, None
    if first_part is not None:
        body = "\n".join(lines[first_part:])
        sums = [sum(m for l in alt.splitlines() if (m := tamil_format.line_marks(l)) is not None)
                for alt in choices.split_alternatives(body)]
        if max(sums, default=0) > 0:
            return max(sums), None
    if q.ocr_part_marks:
        return sum(q.ocr_part_marks), None
    if rule is not None:
        return rule, None
    return None, "Marks not found"


def parse(page_results: list[tuple[dict, Any]]) -> DocumentStructure:
    doc = DocumentStructure()
    qs: list[_Q] = []
    rules: dict[str | None, float | None] = {}
    answer_rules: dict[str, dict] = {}
    section: str | None = None
    section_has_question = False
    fresh_section = False  # a section opened since the last question: its numbering may restart at 1
    part = ""
    pending: list[str] = []  # a passage or poem printed before its question's number

    def open_section(title: str, rest: str) -> None:
        nonlocal section, section_has_question, fresh_section
        section = tamil_format.section_title(title, section) if tamil_format.has_tamil(title) else title.strip()
        section_has_question, fresh_section = False, True
        if section not in doc.sections:
            doc.sections.append(section)
        if rest:
            section_note(rest)

    def section_note(text: str) -> None:
        doc.instructions.append(text)
        rule = tamil_format.section_marks_rule(text)
        if rule is not None:
            rules[section] = rule
        if section:
            _note_answer_rule(answer_rules.setdefault(section, {}), text)

    # A paper with section headings has no question before its first section: numbered header notes
    # ("(1) அனைத்து வினாக்களும் ...", "(2) நீலம் அல்லது கருப்பு ...") are not questions 1 and 2
    has_sections = any(_opens_section(item) for _, res in page_results for item in res.questions)
    group: dict | None = None  # a passage or poem several questions share: {"nums": {12, ..} or empty, "lines": [...]}

    for page_info, page_res in page_results:
        page = page_info["page_number"]
        for item in (piece for block in getattr(page_res, "questions", []) for piece in split_question_blocks(block)):
            text = tamil_format.strip_page_furniture((item.question_text or "").strip())
            label = (item.raw_question_number or "").strip() or None
            if not text and not label:
                continue
            if label and tamil_format.is_rule_line(f"{label} {text}"):
                text, label = f"{label} {text}", None  # "2 × 1 = 2": the OCR took the rule's count for a label
            if item.section and item.section.strip() != section and not label:
                open_section(item.section.strip(), "")
            norm = normalize_question_number(label) if label else None
            cur = qs[-1] if qs else None
            last = cur.num if cur else 0

            # Footer total, header lines, section headings, section notes
            if not label and tamil_format.is_total_line(text):
                continue
            first_line, _, rest = text.partition("\n")
            if _opens_section(item):
                roman = bool(label) and tamil_format.is_roman_section(f"{label}. {text}")
                open_section(f"{label}. {first_line}" if roman else first_line,
                             text if roman or tamil_format.is_roman_section(text) else rest.strip())
                continue
            if not label and not qs and is_document_header(text):
                if (total := extract_exam_total_marks(text)) and not doc.exam_max_marks:
                    doc.exam_max_marks = total
                if not doc.exam_duration_minutes:
                    doc.exam_duration_minutes = tamil_format.duration_minutes(text)
                doc.instructions.append(text)
                continue
            if not label and not section_has_question and is_instruction(text):
                section_note(text)
                continue
            if not label and section_has_question and tamil_format.is_rule_line(text):
                open_section(first_line, text)  # a new set of questions announced by its rule alone ("5 × 2 = 10")
                continue
            if not label and (nums := tamil_format.passage_group(text)) is not None:
                group = {"nums": nums, "lines": [text]}  # "பாடலைப் படித்து ... (12, 13, 14, 15) விடை தருக."
                continue

            # A new question: the next number (or a part of it: "3 (அ)"); in a section whose numbering
            # restarts, 1 again (its questions become "B1", "B2", ... as in English papers)
            top = int(parent_number(norm)) if norm and parent_number(norm).isdigit() else None
            restart = top == 1 and cur is not None and fresh_section
            if (top is not None and (section or not has_sections)
                    and (restart or (last < top <= last + _MAX_SKIP and (cur or top <= _MAX_SKIP)))):
                if restart:
                    part = _PARTS[min(_PARTS.index(part) + 1, len(_PARTS) - 1)] if part else _PARTS[0]
                body = text
                if norm != str(top):
                    body = f"{_shown_part(subpart_path(norm)[0], text)} {text}"
                lines = [*pending, body] if pending else [body]
                if group and (not group["nums"] or top in group["nums"]):
                    context = "\n".join(group["lines"])
                    lines.insert(0, f"[Reading Passage Context]\n{context}\n[/Reading Passage Context]")
                    if not group["nums"] or top >= max(group["nums"]):
                        group = None
                qs.append(_Q(top, lines, section, page, page,
                             item.bbox.model_dump() if getattr(item, "bbox", None) else None, item.confidence,
                             item.question_type, item.marks if norm == str(top) else None,
                             [item.marks] if norm != str(top) and item.marks else [], part))
                pending = []
                section_has_question, fresh_section = True, False
                continue

            if cur is None or (has_sections and not section):
                # Before the first question: a passage for it, or header text the rules above did not know
                if label is None and section and tamil_format.has_tamil(text) and not is_instruction(text):
                    pending.append(text)
                else:
                    doc.instructions.append(text)
                continue
            if group is not None and label is None:
                group["lines"].append(text)  # the shared poem / passage, up to its first question
                continue

            # Everything else belongs to the current question: parts, options, poem, passage, its own note
            if norm and subpart_path(norm) and (parent_number(norm) in ("", str(cur.num))):
                text = f"{_shown_part(subpart_path(norm)[-1], text)} {text}"
                if item.marks:
                    cur.ocr_part_marks.append(item.marks)
            elif label:
                text = f"{label} {text}"  # a number inside the question: a numbered line, a step
            cur.lines.append(text)
            cur.page_end = max(cur.page_end, page)

    out: list[StructuredQuestion] = []
    for q in qs:
        marks, reason = _marks(q, rules.get(q.section))
        number = f"{q.part}{q.num}"
        out.append(StructuredQuestion(
            raw_question_number=number, normalized_number=number, display_number=number,
            question_text="\n".join(l for l in q.lines if l.strip()).strip(), question_type=q.qtype,
            max_marks=marks, section=q.section, page_start=q.page_start, page_end=q.page_end, bbox=q.bbox,
            ocr_confidence=q.confidence, verification_status="NEEDS_REVIEW" if reason else "UNVERIFIED",
            review_reason=reason,
        ))
    doc.questions = _apply_answer_rules(_split_choices(out), answer_rules)
    for sq in doc.questions:
        if sq.question_type:
            sq.type_source = "ocr"
        elif kw := keyword_question_type(sq.question_text):
            sq.question_type, sq.type_source = kw, "rule"
        else:
            sq.question_type, sq.type_source = default_question_type(sq.question_text, sq.max_marks), "default"
    return doc


def uses_pdf_text() -> bool:
    """Whether parsing may read a PDF's own text layer. Not under a Tamil subject: Tamil PDFs often use legacy Tamil
    fonts whose text layer is mojibake ("ம்திப்மொப்ண்கள்" for "மதிப்பெண்கள்"); IndicOCR reads the page image instead."""
    return paper_format.active() != paper_format.TAMIL


def segment_keys(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[Any]:
    """Answer keys of a Tamil key, one per question: "வினா 1. கல்வியின் சிறப்புகள் (2 மதிப்பெண்கள்)" opens a key and
    states its marks; its answer ("விடை:" / "மாதிரி விடை:") and marking scheme ("மதிப்பீட்டுத் திட்டம்:") follow up to
    the next question. Headers, பகுதி headings and the closing total belong to no key."""
    from .key_segmentation import SegmentedKey, _split_choice_keys, _split_part_keys, extract_criteria_from_block, parse_criteria_marks

    tops = sorted({int(p) for q in canonical_questions or []
                   if (p := parent_number(getattr(q, "normalized_number", None) or "")).isdigit()})
    keys: list[dict] = []
    for page_info, page_res in page_results:
        page = page_info["page_number"]
        for item in (piece for block in getattr(page_res, "answers", []) for piece in split_key_blocks(block)):
            text = tamil_format.strip_page_furniture((item.answer_text or "").strip())
            label = (item.question_number or "").strip() or None
            if not text and not label:
                continue
            if not label and (tamil_format.is_total_line(text) or is_section_heading_line(text.partition("\n")[0])):
                continue
            norm = normalize_question_number(label) if label else None
            top = int(parent_number(norm)) if norm and parent_number(norm).isdigit() else None
            last = keys[-1]["num"] if keys else 0
            expected = next((t for t in tops if t > last), None) if tops else last + 1
            if top is not None and top == expected:
                body = text if norm == str(top) else f"{_shown_part(subpart_path(norm)[0], text)} {text}"
                head = body.partition("\n")[0]
                keys.append({"num": top, "lines": [body], "stated": tamil_format.line_marks(head), "item": item,
                             "page": page, "criteria": list(item.criteria or [])})
                continue
            if not keys:
                continue  # the key's title and header
            if norm and subpart_path(norm):
                text = f"{_shown_part(subpart_path(norm)[-1], text)} {text}"
            elif label:
                text = f"{label} {text}"
            keys[-1]["lines"].append(text)
            keys[-1]["criteria"] += [c for c in item.criteria or [] if c not in keys[-1]["criteria"]]

    out = []
    for k in keys:
        full = "\n".join(k["lines"])
        answer, criteria = extract_criteria_from_block(full)
        criteria = criteria or k["criteria"]
        marks = k["stated"] or parse_criteria_marks(criteria, full) or k["item"].marks
        item = k["item"]
        out.append(SegmentedKey(
            raw_question_number=f"Q{k['num']}", normalized_number=str(k["num"]), answer_text=answer or full,
            marks=marks, criteria=criteria, accepted_answers=list(item.accepted_answers or []),
            keywords=list(item.keywords or []), page_number=k["page"],
            bbox=item.bbox.model_dump() if getattr(item, "bbox", None) else None, ocr_confidence=item.confidence))
    return _split_part_keys(_split_choice_keys(out, canonical_questions), canonical_questions)
