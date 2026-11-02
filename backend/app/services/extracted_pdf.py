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


def _markup(value: str | None) -> str:
    return html.escape((value or "").strip()).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>") or "-"


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
        yield image
        yield Paragraph(_markup(item.get("description")), _style("caption", item.get("description", ""), size=8, leading=10,
                                                                 color=colors.HexColor("#62706A"), space_after=5))


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
        if question:
            block.append(Paragraph(_markup(question.question_text), _style("prompt", question.question_text, size=8.5, leading=12,
                                                                           color=colors.HexColor("#5E6A65"), space_after=4)))
        block.append(Paragraph(_markup(key.answer_text), _style("answer", key.answer_text, size=10, leading=15, space_after=4)))
        if key.criteria:
            criteria = [Paragraph("Marking criteria", _style("criteria-title", bold=True, size=9, leading=12, space_after=2))]
            for criterion in key.criteria:
                criteria.append(Paragraph("- " + _markup(criterion), _style("criterion", criterion, size=8.5, leading=12, space_after=1)))
            block.extend(criteria)
        block.extend(_visuals(key.rubric))
        block.append(HRFlowable(width="100%", thickness=.45, color=colors.HexColor("#D6DFDC"), spaceBefore=5, spaceAfter=7))
        story.append(KeepTogether(block))
    return _build(story)
