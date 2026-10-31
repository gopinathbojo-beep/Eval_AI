"""Shared PDF helpers for ADEM documents: fonts, page decorations and math text formatting.
The report and report card themselves are built in school_reports.py.
"""
from __future__ import annotations

import html
import os
import re

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


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
        # The production container runs Linux; Windows-only font lookup loses Unicode symbols.
        linux_fonts = "/usr/share/fonts/truetype/noto"
        noto = os.path.join(linux_fonts, "NotoSans-Regular.ttf")
        noto_bold = os.path.join(linux_fonts, "NotoSans-Bold.ttf")
        if os.path.exists(noto) and os.path.exists(noto_bold):
            for suffix, filename in (("", "Regular"), ("-Bold", "Bold"), ("-Italic", "Italic"), ("-BoldItalic", "BoldItalic")):
                pdfmetrics.registerFont(TTFont("ADEM-Font" + suffix, os.path.join(linux_fonts, f"NotoSans-{filename}.ttf")))
            pdfmetrics.registerFontFamily("ADEM-Font", normal="ADEM-Font", bold="ADEM-Font-Bold",
                                          italic="ADEM-Font-Italic", boldItalic="ADEM-Font-BoldItalic")
            return "ADEM-Font", "ADEM-Font-Bold"
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

