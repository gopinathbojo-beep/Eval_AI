"""Shared PDF helpers for ADEM documents: fonts, page decorations and math text formatting.
The report and report card themselves are built in school_reports.py.
"""
from __future__ import annotations

import html
import os
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


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

    # Step 1: Strip LaTeX math wrappers \( ... \), \[ ... \], \left, \right
    text = re.sub(r"\\left\b", "", text)
    text = re.sub(r"\\right\b", "", text)
    text = re.sub(r"\\\(|\\\)|\\\[|\\\]", "", text)

    # Step 2: Escape basic XML entities
    text = html.escape(text)

    # Step 3: LaTeX math symbols to Unicode equivalents
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

    # Step 4: Handle nested or single \frac{a}{b} -> (a / b)
    while re.search(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", text):
        text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1 / \2)", text)

    # Step 5: Handle \sqrt{a} -> √(a)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)

    # Step 6: Convert exponents (superscripts):
    # e.g., ^(k+1) or ^{k+1} -> <sup>k+1</sup>
    text = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", text)
    text = re.sub(r"\^\(([^\(\)]+)\)", r"<sup>\1</sup>", text)
    # Simple base^power like x^2, 10^3, 2^k, 2^-n
    text = re.sub(r"(?<=[a-zA-Z0-9\)])\^([0-9a-zA-Z+-]+)", r"<sup>\1</sup>", text)

    # Subscripts:
    text = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", text)
    text = re.sub(r"(?<=[a-zA-Z0-9\)])_([0-9a-zA-Z+-]+)", r"<sub>\1</sub>", text)

    # Step 7: Convert newlines to <br/>
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
