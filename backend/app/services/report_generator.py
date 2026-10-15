"""Evaluation Report Generator for ADEM.
Generates an executive, professional PDF evaluation report for a student and exam.
"""
from __future__ import annotations

import html
import io
import os
import re
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from ..deps import err, get_evaluation
from ..models import (
    AnswerKey,
    AuditLog,
    Evaluation,
    EvaluationItem,
    ExamQuestion,
    StudentAnswer,
    Teacher,
)


def _init_fonts() -> tuple[str, str]:
    """Register TTF fonts if available on the host system, with fallback to Helvetica."""
    font_name = "Helvetica"
    font_bold = "Helvetica-Bold"

    windows_font_dir = os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts"
    segoe_path = os.path.join(windows_font_dir, "segoeui.ttf")
    segoe_bold_path = os.path.join(windows_font_dir, "segoeuib.ttf")
    segoe_italic_path = os.path.join(windows_font_dir, "segoeuii.ttf")
    segoe_bi_path = os.path.join(windows_font_dir, "segoeuiz.ttf")

    arial_path = os.path.join(windows_font_dir, "arial.ttf")
    arial_bold_path = os.path.join(windows_font_dir, "arialbd.ttf")
    arial_italic_path = os.path.join(windows_font_dir, "ariali.ttf")
    arial_bi_path = os.path.join(windows_font_dir, "arialbi.ttf")

    try:
        if os.path.exists(segoe_path) and os.path.exists(segoe_bold_path):
            pdfmetrics.registerFont(TTFont("ADEM-Font", segoe_path))
            pdfmetrics.registerFont(TTFont("ADEM-Font-Bold", segoe_bold_path))
            if os.path.exists(segoe_italic_path):
                pdfmetrics.registerFont(TTFont("ADEM-Font-Italic", segoe_italic_path))
            if os.path.exists(segoe_bi_path):
                pdfmetrics.registerFont(TTFont("ADEM-Font-BoldItalic", segoe_bi_path))
            pdfmetrics.registerFontFamily(
                "ADEM-Font",
                normal="ADEM-Font",
                bold="ADEM-Font-Bold",
                italic="ADEM-Font-Italic" if os.path.exists(segoe_italic_path) else "ADEM-Font",
                boldItalic="ADEM-Font-BoldItalic" if os.path.exists(segoe_bi_path) else "ADEM-Font-Bold",
            )
            return "ADEM-Font", "ADEM-Font-Bold"

        if os.path.exists(arial_path) and os.path.exists(arial_bold_path):
            pdfmetrics.registerFont(TTFont("ADEM-Font", arial_path))
            pdfmetrics.registerFont(TTFont("ADEM-Font-Bold", arial_bold_path))
            if os.path.exists(arial_italic_path):
                pdfmetrics.registerFont(TTFont("ADEM-Font-Italic", arial_italic_path))
            if os.path.exists(arial_bi_path):
                pdfmetrics.registerFont(TTFont("ADEM-Font-BoldItalic", arial_bi_path))
            pdfmetrics.registerFontFamily(
                "ADEM-Font",
                normal="ADEM-Font",
                bold="ADEM-Font-Bold",
                italic="ADEM-Font-Italic" if os.path.exists(arial_italic_path) else "ADEM-Font",
                boldItalic="ADEM-Font-BoldItalic" if os.path.exists(arial_bi_path) else "ADEM-Font-Bold",
            )
            return "ADEM-Font", "ADEM-Font-Bold"
    except Exception:
        pass

    return font_name, font_bold


BASE_FONT, BOLD_FONT = _init_fonts()


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that adds running headers and page numbers ('Page X of Y')."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self.doc_title: str = "ADEM Examination Evaluation Report"
        self.header_text: str = ""

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, num_pages: int) -> None:
        width, height = A4
        margin = 36

        self.saveState()
        self.setFont(BASE_FONT, 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Footer on all pages
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(margin, 36, width - margin, 36)
        self.drawString(margin, 24, "ADEM · Digital Examination Management & Evaluation System")
        self.drawRightString(width - margin, 24, f"Page {self._pageNumber} of {num_pages}")

        # Running header on page 2 and later
        if self._pageNumber > 1 and self.header_text:
            self.line(margin, height - 34, width - margin, height - 34)
            self.drawString(margin, height - 26, self.header_text)
            self.drawRightString(width - margin, height - 26, "Official Student Evaluation")

        self.restoreState()


def format_math_text(raw_text: str | None) -> str:
    """Format mathematical expressions and plain text safely for ReportLab Paragraphs."""
    if not raw_text:
        return "&ndash;"

    text = str(raw_text).strip()

    # Step 1: Escape basic XML entities
    text = html.escape(text)

    # Step 2: LaTeX math symbols to Unicode equivalents
    replacements = [
        (r"\\times", "×"),
        (r"\\cdot", "·"),
        (r"\\div", "÷"),
        (r"\\pm", "±"),
        (r"\\leq?", "≤"),
        (r"\\geq?", "≥"),
        (r"\\neq?", "≠"),
        (r"\\approx", "≈"),
        (r"\\infty", "∞"),
        (r"\\pi", "π"),
        (r"\\theta", "θ"),
        (r"\\alpha", "α"),
        (r"\\beta", "β"),
        (r"\\gamma", "γ"),
        (r"\\lambda", "λ"),
        (r"\\sum", "∑"),
        (r"\\int", "∫"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)

    # Step 3: Handle \frac{a}{b} -> (a / b)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1 / \2)", text)

    # Step 4: Handle \sqrt{a} -> √(a)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)

    # Step 5: Convert exponents (superscripts):
    # e.g., ^(k+1) or ^{k+1} -> <sup>k+1</sup>
    text = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", text)
    text = re.sub(r"\^\(([^\(\)]+)\)", r"<sup>\1</sup>", text)
    # Simple base^power like x^2, 10^3, 2^k
    text = re.sub(r"(?<=[a-zA-Z0-9\)])\^([0-9a-zA-Z+-]+)", r"<sup>\1</sup>", text)

    # Subscripts:
    text = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", text)
    text = re.sub(r"(?<=[a-zA-Z0-9\)])_([0-9a-zA-Z+-]+)", r"<sub>\1</sub>", text)

    # Step 6: Convert newlines to <br/>
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "<br/>")

    return text


def _safe_paragraph(content: str, style: ParagraphStyle, fallback_text: str = "") -> Paragraph:
    """Create a Paragraph, safely falling back to plain escaped text if XML parsing fails."""
    try:
        return Paragraph(content, style)
    except Exception:
        fallback = html.escape(fallback_text or content).replace("\n", "<br/>")
        return Paragraph(fallback, style)


def _fmt_marks(v: float | None) -> str:
    if v is None:
        return "–"
    return f"{v:g}"


def build_evaluation_pdf_report(db: Session, teacher: Teacher, evaluation_id: str) -> tuple[bytes, str]:
    """Build and return (pdf_bytes, filename) for the requested evaluation report."""
    ev = get_evaluation(db, teacher, evaluation_id)
    if ev.status != "FINALIZED":
        raise err(
            400,
            "EVALUATION_NOT_FINALIZED",
            f"Official evaluation reports can only be generated for finalized evaluations. Current status is {ev.status}.",
        )

    exam = ev.exam
    student = ev.student
    school_class = student.school_class or exam.school_class
    subject = exam.subject

    # Fetch canonical questions
    questions = (
        db.query(ExamQuestion)
        .filter_by(exam_id=exam.id)
        .order_by(ExamQuestion.position, ExamQuestion.display_number)
        .all()
    )

    # Fetch active mapped answer keys
    keys_map = {
        k.exam_question_id: k
        for k in db.query(AnswerKey)
        .filter_by(exam_id=exam.id, is_active=True, mapping_status="MAPPED")
        .all()
    }

    # Fetch student answers for this evaluation
    answers_map = {
        a.id: a for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    }

    # Fetch evaluation items
    items_map = {
        i.exam_question_id: i
        for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()
    }

    # Fetch audit logs for item overrides
    item_ids = [it.id for it in items_map.values()]
    override_reasons: dict[str, str] = {}
    if item_ids:
        audit_records = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "evaluation_item",
                AuditLog.entity_id.in_(item_ids),
                AuditLog.action.in_(["marks_changed", "item_approved"]),
            )
            .order_by(AuditLog.created_at.desc())
            .all()
        )
        for log in audit_records:
            if log.entity_id not in override_reasons and log.reason:
                override_reasons[log.entity_id] = log.reason

    # Clean student & exam names for filename
    clean_student = re.sub(r"[^\w\-]", "_", student.name.strip())
    clean_roll = re.sub(r"[^\w\-]", "_", student.roll_number.strip())
    clean_exam = re.sub(r"[^\w\-]", "_", exam.name.strip())
    download_filename = f"ADEM_Report_{clean_student}_{clean_roll}_{clean_exam}.pdf"

    # Set up ReportLab Document
    buffer = io.BytesIO()
    margin = 36  # 0.5 in
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=46,
        bottomMargin=46,
    )

    usable_width = A4[0] - 2 * margin  # 523.27 pt

    # Styling
    styles = getSampleStyleSheet()

    c_primary = colors.HexColor("#0F172A")
    c_accent = colors.HexColor("#1D4ED8")
    c_slate = colors.HexColor("#334155")
    c_mute = colors.HexColor("#64748B")
    c_border = colors.HexColor("#E2E8F0")
    c_bg_sunken = colors.HexColor("#F8FAFC")
    c_bg_white = colors.HexColor("#FFFFFF")
    c_warn_bg = colors.HexColor("#FEF3C7")
    c_warn_text = colors.HexColor("#92400E")
    c_warn_border = colors.HexColor("#FDE68A")
    c_ok_bg = colors.HexColor("#DCFCE7")
    c_ok_text = colors.HexColor("#166534")

    style_kicker = ParagraphStyle(
        "Kicker",
        fontName=BOLD_FONT,
        fontSize=8,
        leading=10,
        textColor=c_accent,
        textTransform="uppercase",
        spaceAfter=4,
    )

    style_title = ParagraphStyle(
        "DocTitle",
        fontName=BOLD_FONT,
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=3,
    )

    style_subtitle = ParagraphStyle(
        "DocSub",
        fontName=BASE_FONT,
        fontSize=9.5,
        leading=13,
        textColor=c_mute,
        spaceAfter=12,
    )

    style_sec_header = ParagraphStyle(
        "SecHeader",
        fontName=BOLD_FONT,
        fontSize=12,
        leading=15,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=6,
    )

    style_meta_label = ParagraphStyle(
        "MetaLabel",
        fontName=BOLD_FONT,
        fontSize=8,
        leading=11,
        textColor=c_mute,
    )

    style_meta_val = ParagraphStyle(
        "MetaVal",
        fontName=BASE_FONT,
        fontSize=9,
        leading=12,
        textColor=c_primary,
    )

    style_body = ParagraphStyle(
        "Body",
        fontName=BASE_FONT,
        fontSize=8.5,
        leading=12,
        textColor=c_slate,
    )

    style_body_bold = ParagraphStyle(
        "BodyBold",
        fontName=BOLD_FONT,
        fontSize=8.5,
        leading=12,
        textColor=c_primary,
    )

    style_mono = ParagraphStyle(
        "MonoText",
        fontName=BASE_FONT,
        fontSize=8.5,
        leading=12,
        textColor=c_primary,
    )

    style_q_title = ParagraphStyle(
        "QTitle",
        fontName=BOLD_FONT,
        fontSize=10,
        leading=13,
        textColor=c_primary,
    )

    style_q_score = ParagraphStyle(
        "QScore",
        fontName=BOLD_FONT,
        fontSize=10,
        leading=13,
        textColor=c_accent,
        alignment=2,  # Right aligned
    )

    style_override_notice = ParagraphStyle(
        "OverrideNotice",
        fontName=BOLD_FONT,
        fontSize=8,
        leading=11,
        textColor=c_warn_text,
    )

    style_badge_ok = ParagraphStyle(
        "BadgeOk",
        fontName=BOLD_FONT,
        fontSize=7.5,
        leading=9,
        textColor=c_ok_text,
    )

    story: list[Any] = []

    # -------------------------------------------------------------
    # 1. HEADER SECTION
    # -------------------------------------------------------------
    story.append(Paragraph("ADEM · DIGITAL EXAMINATION MANAGEMENT & EVALUATION", style_kicker))
    story.append(Paragraph("Official Student Examination Report", style_title))
    now_utc = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    finalized_str = (
        ev.finalized_at.strftime("%d %b %Y, %I:%M %p UTC")
        if ev.finalized_at
        else "FINALIZED"
    )
    story.append(
        Paragraph(
            f"Comprehensive question-wise evaluation, grading audit, and marks verification · Report generated on {now_utc}",
            style_subtitle,
        )
    )

    # Divider
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=c_accent,
            spaceBefore=0,
            spaceAfter=10,
        )
    )

    # -------------------------------------------------------------
    # 2. METADATA CARD (2-Column Grid)
    # -------------------------------------------------------------
    col_w = usable_width / 2.0
    meta_left_rows = [
        [
            Paragraph("EXAMINATION", style_meta_label),
            Paragraph(format_math_text(exam.name), style_meta_val),
        ],
        [
            Paragraph("SUBJECT", style_meta_label),
            Paragraph(
                f"{subject.name}{f' ({subject.code})' if subject.code else ''}",
                style_meta_val,
            ),
        ],
        [
            Paragraph("CLASS & YEAR", style_meta_label),
            Paragraph(
                f"{school_class.name if school_class else '–'} · Academic Year {exam.academic_year}",
                style_meta_val,
            ),
        ],
        [
            Paragraph("EXAM TYPE & DATE", style_meta_label),
            Paragraph(
                f"{exam.exam_type}{f' · {exam.exam_date}' if exam.exam_date else ''}{f' · {exam.duration_minutes} mins' if exam.duration_minutes else ''}",
                style_meta_val,
            ),
        ],
        [
            Paragraph("EXAM STATUS", style_meta_label),
            Paragraph(f"<b>{exam.status}</b>", style_meta_val),
        ],
    ]

    meta_right_rows = [
        [
            Paragraph("STUDENT NAME", style_meta_label),
            Paragraph(f"<b>{format_math_text(student.name)}</b>", style_meta_val),
        ],
        [
            Paragraph("ROLL NUMBER", style_meta_label),
            Paragraph(f"<b>{student.roll_number}</b>", style_meta_val),
        ],
        [
            Paragraph("EVALUATOR / TEACHER", style_meta_label),
            Paragraph(f"{teacher.name} ({teacher.email})", style_meta_val),
        ],
        [
            Paragraph("EVALUATION STATUS", style_meta_label),
            Paragraph("<b>FINALIZED</b>", style_meta_val),
        ],
        [
            Paragraph("FINALIZED AT", style_meta_label),
            Paragraph(finalized_str, style_meta_val),
        ],
    ]

    table_left = Table(meta_left_rows, colWidths=[105, col_w - 115])
    table_left.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    table_right = Table(meta_right_rows, colWidths=[115, col_w - 125])
    table_right.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    meta_outer = Table(
        [[table_left, table_right]],
        colWidths=[col_w - 6, col_w - 6],
    )
    meta_outer.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), c_bg_sunken),
                ("BOX", (0, 0), (-1, -1), 1, c_border),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(meta_outer)
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # 3. OVERALL SCORECARD / RESULTS CALLOUT
    # -------------------------------------------------------------
    total_got = ev.total_marks if ev.total_marks is not None else 0.0
    total_max = ev.maximum_marks if ev.maximum_marks is not None else exam.total_marks
    pct = ev.percentage if ev.percentage is not None else (round(100.0 * total_got / total_max, 2) if total_max else 0.0)

    score_w = usable_width / 3.0
    scorecard_data = [
        [
            Paragraph("TOTAL MARKS OBTAINED", style_meta_label),
            Paragraph("OVERALL PERCENTAGE", style_meta_label),
            Paragraph("EXAMINATION RESULT", style_meta_label),
        ],
        [
            Paragraph(
                f"<font size='16' color='#1D4ED8'><b>{_fmt_marks(total_got)}</b></font> <font size='11' color='#64748B'>/ {_fmt_marks(total_max)}</font>",
                style_body_bold,
            ),
            Paragraph(
                f"<font size='16' color='#0F172A'><b>{pct:g}%</b></font>",
                style_body_bold,
            ),
            Paragraph(
                f"<font size='13' color='#166534'><b>FINALIZED</b></font><br/><font size='7.5' color='#64748B'>Teacher Approved & Verified</font>",
                style_body,
            ),
        ],
    ]
    scorecard = Table(scorecard_data, colWidths=[score_w, score_w, score_w])
    scorecard.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#BFDBFE")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DBEAFE")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(scorecard)
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # 4. QUESTION-WISE PERFORMANCE SUMMARY TABLE
    # -------------------------------------------------------------
    story.append(Paragraph("Question-Wise Marks Summary", style_sec_header))

    sum_col_w = [48, usable_width - 48 - 60 - 65 - 65 - 75 - 75, 60, 65, 65, 75, 75]
    # Q#, Section/Description, Max, AI Mark, Awarded, Override?, Status
    sum_headers = [
        Paragraph("<b>Q #</b>", style_body_bold),
        Paragraph("<b>Question Summary</b>", style_body_bold),
        Paragraph("<b>Max</b>", style_body_bold),
        Paragraph("<b>AI Mark</b>", style_body_bold),
        Paragraph("<b>Awarded</b>", style_body_bold),
        Paragraph("<b>Override?</b>", style_body_bold),
        Paragraph("<b>Status</b>", style_body_bold),
    ]
    summary_rows = [sum_headers]

    tot_ai = 0.0
    tot_awarded = 0.0
    tot_max_q = 0.0
    override_count = 0

    for q in questions:
        it = items_map.get(q.id)
        fm = it.final_marks if it else None
        aim = it.ai_marks if it else None
        maxm = q.max_marks or 0.0

        if fm is not None:
            tot_awarded += fm
        if aim is not None:
            tot_ai += aim
        tot_max_q += maxm

        is_overridden = bool(it and it.teacher_overridden)
        if is_overridden:
            override_count += 1

        override_text = "<b>YES</b>" if is_overridden else "No"
        status_text = it.status if it else "PENDING"

        q_summary = q.question_text[:70] + "..." if len(q.question_text) > 70 else (q.question_text or "–")

        summary_rows.append(
            [
                Paragraph(f"<b>Q{q.display_number}</b>", style_body),
                Paragraph(format_math_text(q_summary), style_body),
                Paragraph(_fmt_marks(maxm), style_body),
                Paragraph(_fmt_marks(aim), style_body),
                Paragraph(f"<b>{_fmt_marks(fm)}</b>", style_body_bold),
                Paragraph(
                    f"<font color='{'#92400E' if is_overridden else '#64748B'}'>{override_text}</font>",
                    style_body,
                ),
                Paragraph(status_text, style_body),
            ]
        )

    # Total Row
    summary_rows.append(
        [
            Paragraph("<b>TOTAL</b>", style_body_bold),
            Paragraph(f"<b>All Questions ({len(questions)} items)</b>", style_body_bold),
            Paragraph(f"<b>{_fmt_marks(tot_max_q)}</b>", style_body_bold),
            Paragraph(f"<b>{_fmt_marks(tot_ai)}</b>", style_body_bold),
            Paragraph(f"<font color='#1D4ED8'><b>{_fmt_marks(tot_awarded)}</b></font>", style_body_bold),
            Paragraph(
                f"<b>{override_count} change{'s' if override_count != 1 else ''}</b>",
                style_body_bold,
            ),
            Paragraph(f"<b>{pct:g}%</b>", style_body_bold),
        ]
    )

    summary_table = Table(summary_rows, colWidths=sum_col_w, repeatRows=1)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("BOX", (0, 0), (-1, -1), 1, c_border),
                ("INNERGRID", (0, 0), (-1, -2), 0.5, c_border),
                # Alternating row background
                *[
                    ("BACKGROUND", (0, i), (-1, i), c_bg_sunken)
                    for i in range(1, len(summary_rows) - 1, 2)
                ],
                # Total row styling
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
                ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#94A3B8")),
            ]
        )
    )
    # Style header text in white
    for cell in summary_rows[0]:
        if isinstance(cell, Paragraph):
            cell.style.textColor = colors.white

    story.append(summary_table)
    story.append(Spacer(1, 14))

    # -------------------------------------------------------------
    # 5. DETAILED QUESTION-BY-QUESTION EVALUATION BREAKDOWN
    # -------------------------------------------------------------
    story.append(Paragraph("Detailed Question-Wise Evaluation Record", style_sec_header))
    story.append(
        Paragraph(
            "Below is the complete audit record for each question, including official answer expectations, transcribed student responses, AI evaluation notes, and teacher verification.",
            style_subtitle,
        )
    )

    for idx, q in enumerate(questions, 1):
        it = items_map.get(q.id)
        ans = answers_map.get(it.student_answer_id) if it and it.student_answer_id else None
        key = keys_map.get(q.id)

        fm = it.final_marks if it else None
        aim = it.ai_marks if it else None
        maxm = q.max_marks or 0.0
        is_overridden = bool(it and it.teacher_overridden)
        override_reason = override_reasons.get(it.id) if (it and is_overridden) else None

        card_flowables: list[Any] = []

        # Card Header: Question title & score
        section_info = f" · Section: {q.section}" if q.section else ""
        q_hdr_left = Paragraph(
            f"<b>Question {q.display_number}</b>{section_info}",
            style_q_title,
        )
        q_hdr_right = Paragraph(
            f"Awarded: <b>{_fmt_marks(fm)}</b> / {_fmt_marks(maxm)} Marks",
            style_q_score,
        )

        hdr_table = Table(
            [[q_hdr_left, q_hdr_right]],
            colWidths=[usable_width - 150, 150],
        )
        hdr_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ]
            )
        )
        card_flowables.append(hdr_table)

        # Teacher Override Notice Banner (if overridden)
        if is_overridden:
            reason_part = f" · <b>Recorded Reason:</b> {html.escape(override_reason)}" if override_reason else ""
            override_msg = (
                f"⚠ <b>TEACHER OVERRIDE:</b> The AI originally evaluated this answer as <b>{_fmt_marks(aim)} marks</b>. "
                f"The teacher adjusted the final awarded score to <b>{_fmt_marks(fm)} marks</b>.{reason_part}"
            )
            banner_table = Table(
                [[Paragraph(override_msg, style_override_notice)]],
                colWidths=[usable_width],
            )
            banner_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_warn_bg),
                        ("BOX", (0, 0), (-1, -1), 1, c_warn_border),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            card_flowables.append(banner_table)

        # Question Prompt
        q_text_content = format_math_text(q.question_text) or "<i>(No question text recorded)</i>"
        q_block = Table(
            [
                [
                    Paragraph("<b>QUESTION PROMPT:</b>", style_meta_label),
                ],
                [
                    Paragraph(q_text_content, style_body),
                ],
            ],
            colWidths=[usable_width],
        )
        q_block.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), c_bg_sunken),
                    ("BOX", (0, 0), (-1, -1), 0.5, c_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        card_flowables.append(q_block)

        # Answers Comparison: Official Key vs Student Answer
        official_ans_text = (
            format_math_text(key.answer_text) if (key and key.answer_text) else "<i>(No official answer mapped)</i>"
        )
        student_ans_text = (
            format_math_text(ans.answer_text) if (ans and ans.answer_text) else "<font color='#DC2626'><i>(No student answer submitted / not attempted)</i></font>"
        )

        # Add criteria or keywords if available
        if key and key.keywords:
            official_ans_text += f"<br/><font size='7.5' color='#64748B'><b>Keywords:</b> {html.escape(', '.join(key.keywords))}</font>"
        if key and key.criteria:
            crit_items = "<br/>".join([f"• {html.escape(str(c))}" for c in key.criteria])
            official_ans_text += f"<br/><font size='7.5' color='#64748B'><b>Marking Criteria:</b><br/>{crit_items}</font>"

        answers_table = Table(
            [
                [
                    Paragraph("<b>OFFICIAL ANSWER KEY</b>", style_meta_label),
                    Paragraph("<b>STUDENT SUBMISSION (TRANSCRIBED)</b>", style_meta_label),
                ],
                [
                    Paragraph(official_ans_text, style_mono),
                    Paragraph(student_ans_text, style_mono),
                ],
            ],
            colWidths=[usable_width / 2.0, usable_width / 2.0],
        )
        answers_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), c_bg_white),
                    ("BOX", (0, 0), (-1, -1), 0.5, c_border),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        card_flowables.append(answers_table)

        # AI Evaluation & Teacher Feedback Block
        ai_feedback_str = (
            format_math_text(it.ai_feedback)
            if (it and it.ai_feedback)
            else "<i>No automated feedback generated.</i>"
        )

        matched_p = (
            "<br/>".join([f"✓ {html.escape(str(p))}" for p in it.matched_points])
            if (it and it.matched_points)
            else ""
        )
        missing_p = (
            "<br/>".join([f"✗ {html.escape(str(p))}" for p in it.missing_points])
            if (it and it.missing_points)
            else ""
        )

        ai_details_parts = [
            f"<b>AI Decision:</b> {it.ai_decision or 'EVALUATED'} &nbsp;|&nbsp; <b>AI Suggested Marks:</b> {_fmt_marks(aim)} / {_fmt_marks(maxm)}"
        ]
        if it and it.ai_confidence is not None:
            ai_details_parts[0] += f" &nbsp;|&nbsp; <b>Confidence:</b> {it.ai_confidence * 100:.0f}%"

        ai_details_parts.append(f"<b>Feedback:</b> {ai_feedback_str}")
        if matched_p:
            ai_details_parts.append(f"<font color='#166534'><b>Matched Key Points:</b><br/>{matched_p}</font>")
        if missing_p:
            ai_details_parts.append(f"<font color='#B91C1C'><b>Missing Expected Points:</b><br/>{missing_p}</font>")

        ai_full_text = "<br/>".join(ai_details_parts)

        # Teacher review column
        teacher_notes = []
        teacher_notes.append(f"<b>Approved Marks:</b> {_fmt_marks(fm)} / {_fmt_marks(maxm)}")
        teacher_notes.append(f"<b>Item Status:</b> {it.status if it else 'PENDING'}")
        if is_overridden:
            teacher_notes.append("<font color='#92400E'><b>Teacher Override Applied: Yes</b></font>")
            if override_reason:
                teacher_notes.append(f"<b>Reason:</b> {html.escape(override_reason)}")
        else:
            teacher_notes.append("<b>Teacher Override Applied:</b> No (AI mark accepted)")

        if it and it.teacher_feedback:
            teacher_notes.append(f"<b>Teacher Notes:</b> {html.escape(it.teacher_feedback)}")

        eval_breakdown_table = Table(
            [
                [
                    Paragraph("<b>AI EVALUATION DETAILS</b>", style_meta_label),
                    Paragraph("<b>TEACHER AUDIT & VERIFICATION</b>", style_meta_label),
                ],
                [
                    Paragraph(ai_full_text, style_body),
                    Paragraph("<br/>".join(teacher_notes), style_body),
                ],
            ],
            colWidths=[usable_width * 0.60, usable_width * 0.40],
        )
        eval_breakdown_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), c_bg_sunken),
                    ("BOX", (0, 0), (-1, -1), 0.5, c_border),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        card_flowables.append(eval_breakdown_table)

        # Wrap question block so that question header + prompt don't get orphaned if possible
        story.append(KeepTogether(card_flowables[:3]))
        story.extend(card_flowables[3:])
        story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # 6. REPORT SIGN-OFF & CERTIFICATION FOOTNOTE
    # -------------------------------------------------------------
    signoff_text = (
        f"<b>Official Assessment Record</b> · Certified by {teacher.name} ({teacher.email}) · "
        f"Generated from ADEM local verified database. All teacher approvals, overrides, and timestamps are audited. "
        f"Record ID: {ev.id}"
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=c_border,
            spaceBefore=8,
            spaceAfter=6,
        )
    )
    story.append(Paragraph(signoff_text, style_subtitle))

    # Build PDF with NumberedCanvas
    def canvas_maker(*args: Any, **kwargs: Any) -> NumberedCanvas:
        c = NumberedCanvas(*args, **kwargs)
        c.header_text = f"{exam.name} · {student.name} ({student.roll_number})"
        return c

    doc.build(story, canvasmaker=canvas_maker)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes, download_filename
