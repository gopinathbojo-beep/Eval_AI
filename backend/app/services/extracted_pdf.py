"""Printable exports of the reviewed, canonical question and answer-key rows."""
from __future__ import annotations

from io import BytesIO
import html
import os
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..documents.cloud import hydrate
from ..documents.storage import abs_path
from .report_generator import BASE_FONT, BOLD_FONT


_registered: dict[str, tuple[str, str]] = {}


def _script(text: str) -> str:
    if re.search(r"[\u0b80-\u0bff]", text):
        return "tamil"
    if re.search(r"[\u0900-\u097f]", text):
        return "devanagari"
    return "latin"


def _script_fonts(script: str) -> tuple[str, str]:
    if script == "latin":
        return BASE_FONT, BOLD_FONT
    if script in _registered:
        return _registered[script]
    family = "Tamil" if script == "tamil" else "Devanagari"
    candidates = [
        (f"/usr/share/fonts/truetype/noto/NotoSans{family}-Regular.ttf",
         f"/usr/share/fonts/truetype/noto/NotoSans{family}-Bold.ttf"),
        (os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "Nirmala.ttf"),
         os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "NirmalaB.ttf")),
    ]
    for regular, bold in candidates:
        if Path(regular).is_file():
            normal_name, bold_name = f"Eval-{family}", f"Eval-{family}-Bold"
            if normal_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(normal_name, regular))
                pdfmetrics.registerFont(TTFont(bold_name, bold if Path(bold).is_file() else regular))
            _registered[script] = (normal_name, bold_name)
            return _registered[script]
    return BASE_FONT, BOLD_FONT


def _style(name: str, text: str = "", *, size=10, leading=14, bold=False, color=colors.HexColor("#26332F"),
           align=0, space_after=0):
    normal, strong = _script_fonts(_script(text))
    return ParagraphStyle(name, fontName=strong if bold else normal, fontSize=size, leading=leading,
                          textColor=color, alignment=align, spaceAfter=space_after)


_SYMBOL_FONTS = [
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "seguisym.ttf"),
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
]
_symbols: dict[str, object] = {}


def _symbol_font():
    """A fallback font for maths symbols the body font lacks (Segoe UI has no ⇒ or ∠)."""
    if "font" not in _symbols:
        _symbols["font"] = None
        for path in _SYMBOL_FONTS:
            if Path(path).is_file():
                pdfmetrics.registerFont(TTFont("Eval-Symbols", path))
                _symbols["font"] = ("Eval-Symbols", pdfmetrics.getFont("Eval-Symbols").face.charToGlyph)
                break
    return _symbols["font"]


def _has_glyph(font_name: str, char: str) -> bool:
    cmap = getattr(pdfmetrics.getFont(font_name).face, "charToGlyph", None)
    return cmap is None or ord(char) in cmap  # a built-in font (Helvetica) has no map to check


def _markup(value: str | None) -> str:
    text = (value or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return "-"
    fallback = _symbol_font()
    out = []
    for char in text:
        piece = "<br/>" if char == "\n" else html.escape(char)
        if (fallback and ord(char) > 0x7f and not char.isspace() and not _has_glyph(BASE_FONT, char)
                and ord(char) in fallback[1]):
            piece = f'<font name="{fallback[0]}">{piece}</font>'
        out.append(piece)
    return "".join(out)


def _half(value: float) -> str:
    whole, frac = int(value), value - int(value)
    if abs(frac - .5) < 1e-6:
        return f"{whole}½" if whole else "½"
    return f"{value:g}"


def _criteria_lines(node, out=None):
    """Every scoring step of the marking scheme with its marks; OR between alternatives."""
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    children = [c for c in node.get("children") or [] if c.get("kind") != "context"]
    if not children:
        if node.get("marks") is not None:
            text = (node.get("text") or node.get("label") or "").strip()
            out.append(f"{text} — {_half(node['marks'])}" if text else _half(node["marks"]))
        return out
    for index, child in enumerate(children):
        if node.get("kind") == "choose" and index:
            out.append("OR")
        if child.get("audience") == "accessible":
            out.append("For visually impaired candidates:")
        _criteria_lines(child, out)
    return out


def _visuals(structure: dict | None):
    for item in (structure or {}).get("visuals", []):
        stored = item.get("crop_file")
        if not stored:
            continue
        path = hydrate(abs_path(stored))
        if not path.is_file():
            continue
        image = Image(str(path))
        image._restrictSize(165 * mm, 70 * mm)
        yield image  # the printed table or figure itself; the AI's own description of it is not printed text
        yield Spacer(1, 5)


def _header(story, exam, title: str, count: int):
    story.append(Paragraph("Eval AI", _style("brand", bold=True, size=9, leading=11, color=colors.HexColor("#0F766E"))))
    story.append(Paragraph(_markup(title), _style("title", title, bold=True, size=19, leading=23, space_after=4)))
    details = [
        ["Exam", exam.name],
        ["Class", exam.school_class.name if exam.school_class else "-"],
        ["Subject", exam.subject.name if exam.subject else "-"],
        ["Academic year", exam.academic_year],
        ["Maximum marks", f"{exam.total_marks:g}"],
        ["Rows", str(count)],
    ]
    table = Table([[Paragraph(f"<b>{html.escape(label)}</b>", _style("meta-label", bold=True, size=8.5, leading=11)),
                    Paragraph(_markup(value), _style("meta-value", str(value), size=8.5, leading=11))]
                   for label, value in details], colWidths=[34 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E7F3F1")),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#B7CCC7")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#D8E4E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([table, Spacer(1, 7 * mm)])


def _page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#C9D7D3"))
    canvas.line(doc.leftMargin, 13 * mm, A4[0] - doc.rightMargin, 13 * mm)
    canvas.setFont(BASE_FONT, 7.5)
    canvas.setFillColor(colors.HexColor("#68756F"))
    canvas.drawString(doc.leftMargin, 8 * mm, "Generated from reviewed Eval AI extraction")
    canvas.drawRightString(A4[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _build(story) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                 topMargin=16 * mm, bottomMargin=20 * mm,
                                 title="Eval AI extracted document", author="Eval AI")
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return output.getvalue()


def questions_pdf(exam, questions) -> bytes:
    story = []
    _header(story, exam, "Extracted Question Paper", len(questions))
    current_section = None
    for question in questions:
        section = question.section or "General"
        if section != current_section:
            if current_section is not None:
                story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(_markup(section), _style("section", section, bold=True, size=12, leading=15,
                                                            color=colors.HexColor("#0F766E"), space_after=5)))
            current_section = section
        marks = "-" if question.max_marks is None else f"{question.max_marks:g} marks"
        heading = f"Question {html.escape(question.display_number)}  |  {marks}"
        story.append(Paragraph(heading, _style("question-heading", heading, bold=True, size=11, leading=14, space_after=4)))
        structure = question.structure or {}
        _note(story, "Review notes", structure.get("issues") or ([question.review_reason] if question.review_reason else []))
        story.append(Paragraph(_markup(question.question_text), _style("question", question.question_text, size=10, leading=15,
                                                                      space_after=5)))
        story.extend(_visuals(question.structure))
        story.append(HRFlowable(width="100%", thickness=.45, color=colors.HexColor("#D6DFDC"), spaceBefore=4, spaceAfter=7))
    return _build(story)


def answer_keys_pdf(exam, keys, questions_by_id) -> bytes:
    story = []
    _header(story, exam, "Extracted Answer Key / Marking Scheme", len(keys))
    for key in keys:
        question = questions_by_id.get(key.exam_question_id)
        label = question.display_number if question else (key.raw_question_number or "Unmapped")
        marks = key.marks if key.marks is not None else (question.max_marks if question else None)
        heading = f"Question {html.escape(label)}" + (f"  |  {marks:g} marks" if marks is not None else "")
        block = [Paragraph(heading, _style("key-heading", heading, bold=True, size=11, leading=14, space_after=3))]
        notes = list((key.rubric or {}).get("problems") or [])
        if key.mapping_note and key.mapping_status != "MAPPED":
            notes.append(key.mapping_note)
        _note(block, "Review notes", notes)
        if question:
            block.append(Paragraph(_markup(question.question_text), _style("prompt", question.question_text, size=8.5, leading=12,
                                                                           color=colors.HexColor("#5E6A65"), space_after=4)))
        block.append(Paragraph(_markup(key.answer_text), _style("answer", key.answer_text, size=10, leading=15, space_after=4)))
        steps = _criteria_lines((key.rubric or {}).get("cbse_tree")) or list(key.criteria or [])
        if steps:
            criteria = [Paragraph("Marking criteria", _style("criteria-title", bold=True, size=9, leading=12, space_after=2))]
            for criterion in steps:
                heading = criterion == "OR" or criterion.endswith(":")
                criteria.append(Paragraph(("" if heading else "- ") + _markup(criterion), _style("criterion", criterion, size=8.5, leading=12, space_after=1)))
            block.extend(criteria)
        block.extend(_visuals(key.rubric))
        block.append(HRFlowable(width="100%", thickness=.45, color=colors.HexColor("#D6DFDC"), spaceBefore=5, spaceAfter=7))
        story.append(KeepTogether(block))
    return _build(story)


# ---- Extraction reports: everything the AI read and flagged, for checking against the uploaded file ----

def _note(story, title: str, lines, color="#B42318"):
    lines = [x for x in (lines or []) if x]
    if not lines:
        return
    story.append(Paragraph(_markup(title), _style("note-title", title, bold=True, size=8.5, leading=11,
                                                 color=colors.HexColor(color), space_after=1)))
    for line in lines:
        text = "- " + str(line)
        story.append(Paragraph(_markup(text), _style("note", text, size=8.5, leading=11.5,
                                                     color=colors.HexColor(color), space_after=1)))


def _plain(story, label: str, value):
    if value in (None, "", [], {}):
        return
    text = f"{label}: {value}"
    story.append(Paragraph(_markup(text), _style("plain", text, size=8.5, leading=11.5,
                                                 color=colors.HexColor("#5E6A65"), space_after=1)))


def _body(story, text):
    if text:
        story.append(Paragraph(_markup(text), _style("body", text, size=10, leading=14.5, space_after=3)))


def _tree_lines(node, depth=0, out=None):
    """The scoring tree as indented lines: id, kind, marks, label and the start of its text."""
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    marks = "" if node.get("marks") is None else f" [{node['marks']:g}]"
    extra = f" limit {node['limit']}" if node.get("limit") else ""
    audience = f" audience={node['audience']}" if node.get("audience") else ""
    text = " ".join((node.get("label") or "", (node.get("text") or "")[:110])).strip()
    out.append(f"{'. ' * depth}{node.get('id')} ({node.get('kind')}{extra}{audience}){marks} {text}".rstrip())
    for child in node.get("children") or []:
        _tree_lines(child, depth + 1, out)
    return out


def _document(story, title: str, doc):
    story.append(Paragraph(_markup(title), _style("doc-title", title, bold=True, size=12, leading=15,
                                                 color=colors.HexColor("#0F766E"), space_after=3)))
    if doc is None:
        _plain(story, "File", "not uploaded")
        return
    _plain(story, "File", doc.original_filename)
    _plain(story, "Status", f"{doc.status}" + (f" ({doc.stage})" if doc.stage else ""))
    _note(story, "Document error", [doc.error_message])
    for page in doc.pages or []:
        state = page.get("ocr_status") or "not read"
        _plain(story, f"Page {page.get('page_number')}", state + (f" - {page['ocr_error']}" if page.get("ocr_error") else ""))
    extraction = getattr(doc, "extraction", None) or {}
    _note(story, "Document issues reported by the AI", extraction.get("issues"))
    story.append(Spacer(1, 4 * mm))


def _rule(story):
    story.append(HRFlowable(width="100%", thickness=.45, color=colors.HexColor("#D6DFDC"), spaceBefore=4, spaceAfter=6))


def _part(story, title: str):
    story.append(Paragraph(_markup(title), _style("part", title, bold=True, size=14, leading=18, space_after=4)))


def _heading(story, text: str):
    story.append(Paragraph(_markup(text), _style("item-head", text, bold=True, size=10.5, leading=13.5, space_after=2)))


def exam_extraction_report_pdf(exam, paper_doc, key_doc, questions, keys) -> bytes:
    """Question paper and answer key as extracted, with every review note, for checking against the uploads."""
    story = []
    _header(story, exam, "Extraction Report: Question Paper and Answer Key", len(questions) + len(keys))
    _document(story, "Question paper file", paper_doc)
    _document(story, "Answer key file", key_doc)
    _part(story, "Questions")
    for question in questions:
        marks = "-" if question.max_marks is None else f"{question.max_marks:g} marks"
        _heading(story, f"Question {question.display_number}  |  Section {question.section or '-'}  |  {marks}  |  "
                        f"{question.verification_status}")
        structure = question.structure or {}
        _note(story, "Review notes", structure.get("issues") or ([question.review_reason] if question.review_reason else []))
        _plain(story, "Pages", structure.get("source_pages") or
               "-".join(str(p) for p in (question.page_start, question.page_end) if p))
        _body(story, question.question_text)
        _note(story, "Scoring structure", _tree_lines(structure.get("cbse_tree") or structure.get("tree")), color="#475467")
        _rule(story)
    _part(story, "Answer key")
    by_id = {q.id: q for q in questions}
    for key in keys:
        question = by_id.get(key.exam_question_id)
        label = question.display_number if question else f"{key.raw_question_number or '?'} (not mapped)"
        marks = "-" if key.marks is None else f"{key.marks:g} marks"
        _heading(story, f"Answer {label}  |  {marks}  |  {key.mapping_status}  |  {key.verification_status}")
        rubric = key.rubric or {}
        notes = list(rubric.get("problems") or [])
        if key.mark_mismatch and question:
            notes.append(f"Key marks {key.marks} differ from the question's {question.max_marks}")
        _note(story, "Review notes", notes)
        _plain(story, "Mapping", key.mapping_note)
        _plain(story, "Pages", rubric.get("source_pages") or key.page_number)
        _body(story, key.answer_text)
        _note(story, "Marking criteria", key.criteria, color="#475467")
        _note(story, "Scoring structure", _tree_lines(rubric.get("cbse_tree")), color="#475467")
        _rule(story)
    return _build(story)


def sheet_extraction_report_pdf(exam, evaluation, sheet_doc, answers, items, questions) -> bytes:
    """A student's sheet as read, how each answer was mapped, and the AI's grading notes."""
    story = []
    _header(story, exam, "Extraction Report: Student Answer Sheet", len(answers))
    student = evaluation.student
    _plain(story, "Student", (student.name if student.name.strip() == f"Roll {student.roll_number}"
                             else f"{student.name} (roll {student.roll_number})") if student else "-")
    total = "-" if evaluation.total_marks is None else f"{evaluation.total_marks:g}"
    maximum = "-" if evaluation.maximum_marks is None else f"{evaluation.maximum_marks:g}"
    _plain(story, "Evaluation", f"{evaluation.status}, total {total} / {maximum}")
    _document(story, "Answer sheet file", sheet_doc)
    identity = (getattr(sheet_doc, "identity", None) or {}) if sheet_doc else {}
    _plain(story, "Student details read from the sheet", identity.get("read"))
    _plain(story, "Identity match", identity.get("note"))
    by_id = {q.id: q for q in questions}
    _part(story, "Answers as read")
    for answer in answers:
        question = by_id.get(answer.exam_question_id)
        target = question.display_number if question else "not mapped"
        _heading(story, f"Written as {answer.raw_question_number or '?'}  ->  Question {target}  |  "
                        f"page {answer.page_number or '-'}  |  {answer.status}")
        _note(story, "Mapping note", [answer.mapping_note])
        _plain(story, "Reading confidence", None if answer.ocr_confidence is None else f"{answer.ocr_confidence:.2f}")
        _body(story, answer.raw_ocr_text)
        if answer.answer_text and answer.answer_text != answer.raw_ocr_text:
            _plain(story, "Edited by teacher", answer.answer_text)
        _rule(story)
    _part(story, "Grading")
    for item in sorted(items, key=lambda i: by_id[i.exam_question_id].position if i.exam_question_id in by_id else 0):
        question = by_id.get(item.exam_question_id)
        top = "-" if not question or question.max_marks is None else f"{question.max_marks:g}"
        awarded = "-" if item.ai_marks is None else f"{item.ai_marks:g}"
        _heading(story, f"Question {question.display_number if question else '?'}  |  AI {awarded} / {top}  |  "
                        f"{item.ai_decision or '-'}  |  {item.status}")
        _note(story, "Error", [item.error])
        _plain(story, "AI confidence", None if item.ai_confidence is None else f"{item.ai_confidence:.2f}")
        _plain(story, "AI feedback", item.ai_feedback)
        _note(story, "Matched points", item.matched_points, color="#067647")
        _note(story, "Missing points", item.missing_points)
        if item.final_marks is not None or item.teacher_feedback:
            final = "-" if item.final_marks is None else f"{item.final_marks:g}"
            _plain(story, "Teacher", f"{final} marks" + (f", {item.teacher_feedback}" if item.teacher_feedback else ""))
        _rule(story)
    return _build(story)
