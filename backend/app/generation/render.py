"""The generated paper as two A4 PDFs: the question paper, and the marking scheme (answers, marking points, sources)."""
from __future__ import annotations

import io
from html import escape

import pymupdf

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 14pt; text-align: center; margin: 0 0 2pt 0; }
.meta { text-align: center; font-size: 10pt; margin-bottom: 6pt; }
h2 { font-size: 11.5pt; text-align: center; margin: 12pt 0 4pt 0; }
.ins { font-size: 9.5pt; }
table.q { width: 100%; margin: 0 0 6pt 0; }
td.n { width: 28pt; vertical-align: top; font-weight: bold; }
td.m { width: 34pt; vertical-align: top; text-align: right; }
td.t { vertical-align: top; }
.or { text-align: center; font-weight: bold; margin: 2pt 0; }
.ans { margin: 2pt 0 2pt 0; }
.pts { font-size: 9.5pt; }
.src { font-size: 8.5pt; color: #555555; }
"""


def _text(s: str) -> str:
    return escape(s or "").replace("\n", "<br/>")


def _options(opts: list[str]) -> str:
    return "<br/>".join(f"({chr(97 + i)}) {_text(o)}" for i, o in enumerate(opts))


def _body(q: dict) -> str:
    out = _text(q["text"])
    if q.get("options"):
        out += "<br/>" + _options(q["options"])
    return out


def _header(paper: dict, key: bool) -> str:
    hours = paper.get("duration_minutes", 180) / 60
    h = [f"<h1>{_text(paper.get('title', 'Question Paper'))}{' - Marking Scheme' if key else ''}</h1>",
         f"<p class='meta'>Class {paper.get('standard', '')} &nbsp;|&nbsp; {_text(paper.get('subject_name', ''))}"
         f" &nbsp;|&nbsp; Time: {hours:g} hours &nbsp;|&nbsp; Maximum Marks: {paper.get('total_marks', 0):g}</p>"]
    if not key and paper.get("instructions"):
        h.append("<p class='ins'><b>General Instructions:</b><br/>"
                 + "<br/>".join(f"{i}. {_text(x)}" for i, x in enumerate(paper["instructions"], 1)) + "</p>")
    return "".join(h)


def _row(number: str, body: str, marks: str) -> str:
    return f"<table class='q'><tr><td class='n'>{number or '&nbsp;'}</td><td class='t'>{body}</td><td class='m'>{marks}</td></tr></table>"


def paper_html(paper: dict) -> str:
    parts, section = [_header(paper, False)], None
    for q in paper.get("questions", []):
        if q["section"] != section:
            section = q["section"]
            parts.append(f"<h2>SECTION {escape(section)}</h2>")
        parts.append(_row(f"{q['number']}.", _body(q), f"[{q['marks']:g}]"))
        if q.get("or"):
            parts.append("<p class='or'>OR</p>")
            parts.append(_row("", _body(q["or"]), f"[{q['marks']:g}]"))
    return "".join(parts)


def _answer(q: dict) -> str:
    out = f"<p class='ans'><b>Answer:</b> {_text(q.get('answer', ''))}</p>"
    if q.get("marking_points"):
        out += "<p class='pts'>" + "<br/>".join(f"&bull; {_text(p['point'])} ({p['marks']:g})" for p in q["marking_points"]) + "</p>"
    if q.get("sources"):
        out += "<p class='src'>Source: " + "; ".join(f"{_text(s['chapter'])}, p.{s['pages']}" for s in q["sources"]) + "</p>"
    return out


def key_html(paper: dict) -> str:
    parts, section = [_header(paper, True)], None
    for q in paper.get("questions", []):
        if q["section"] != section:
            section = q["section"]
            parts.append(f"<h2>SECTION {escape(section)}</h2>")
        parts.append(_row(f"{q['number']}.", _body(q) + _answer(q), f"[{q['marks']:g}]"))
        if q.get("or"):
            parts.append("<p class='or'>OR</p>")
            parts.append(_row("", _body(q["or"]) + _answer(q["or"]), f"[{q['marks']:g}]"))
    return "".join(parts)


def to_pdf(html: str) -> bytes:
    story = pymupdf.Story(html=f"<body>{html}</body>", user_css=CSS)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page = pymupdf.paper_rect("a4")
    where = page + (45, 45, -45, -45)
    more = 1
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def paper_pdf(paper: dict) -> bytes:
    return to_pdf(paper_html(paper))


def key_pdf(paper: dict) -> bytes:
    return to_pdf(key_html(paper))
