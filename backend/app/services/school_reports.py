"""Printable school documents: the per-exam student report and the term report card.

Layout comes from a template config (see report_templates.py): which sections appear and in what order, table
columns, summary items, every label, styling and signature lines. Data is gathered into plain dicts first, so the
same renderer draws real records and the sample data used by the template editor's preview.
Grades follow the CBSE 8-point scale; marks come only from finalized evaluations.
"""
from __future__ import annotations

import html
import io
import math
import re
from types import SimpleNamespace
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from ..deps import err, get_evaluation
from ..documents.storage import abs_path
from ..models import AuditLog, Evaluation, EvaluationItem, Exam, ExamQuestion, SchoolClass, SchoolProfile, Student, Teacher
from .k_level import K_LEVELS, summarize as summarize_outcomes
from .report_generator import BASE_FONT, BOLD_FONT
from .report_templates import active_config

# CBSE 8-point scale: (lowest percentage, grade)
CBSE_GRADES = [(91, "A1"), (81, "A2"), (71, "B1"), (61, "B2"), (51, "C1"), (41, "C2"), (33, "D"), (0, "E")]
GRADE_SCALE_TEXT = "A1 91–100 · A2 81–90 · B1 71–80 · B2 61–70 · C1 51–60 · C2 41–50 · D 33–40 · E below 33"
_FONTS = {"default": (BASE_FONT, BOLD_FONT), "helvetica": ("Helvetica", "Helvetica-Bold"),
          "times": ("Times-Roman", "Times-Bold")}
MUTE = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
ZEBRA = colors.HexColor("#F1F5F9")
TOTAL_BG = colors.HexColor("#E2E8F0")


def cbse_grade(percentage: float | None) -> str:
    if percentage is None:
        return "–"
    p = math.floor(percentage + 0.5)  # 90.5% counts as 91 (round() would give 90)
    return next(g for low, g in CBSE_GRADES if p >= low)


def _m(v: float | None) -> str:
    return "–" if v is None else f"{v:g}"


def _pct(got: float | None, mx: float | None) -> float | None:
    return round(100.0 * got / mx, 2) if got is not None and mx else None


def _esc(t: Any) -> str:
    return html.escape("" if t is None else str(t)).replace("\n", "<br/>")


def _clean_name(*parts: str) -> str:
    return "_".join(re.sub(r"[^\w\-]", "_", p.strip()) for p in parts if p)


def _school(profile: SchoolProfile | None) -> dict:
    logo = None
    if profile and profile.logo_file:
        try:
            p = abs_path(profile.logo_file)
            logo = p if p.is_file() else None
        except Exception:
            logo = None
    return {"name": (profile.name or "").strip() if profile else "", "address": (profile.address or "").strip() if profile else "",
            "principal_name": (profile.principal_name or "").strip() if profile else "", "logo": logo}


class _Doc:
    """Styles and building blocks for one template."""

    def __init__(self, cfg: dict, school: dict):
        self.cfg, self.school, self.L = cfg, school, cfg["labels"]
        st = cfg["style"]
        self.font, self.bold = _FONTS.get(st["font"], _FONTS["default"])
        self.fs = st["font_size"]
        self.accent = colors.HexColor(st["accent"])
        self.page = LETTER if st["paper"] == "Letter" else A4
        self.margin = 40
        self.width = self.page[0] - 2 * self.margin

    def style(self, size: float | None = None, bold: bool = False, color=colors.HexColor("#0F172A"), align=TA_LEFT,
              leading: float | None = None) -> ParagraphStyle:
        size = size or self.fs
        return ParagraphStyle("s", fontName=self.bold if bold else self.font, fontSize=size, leading=leading or size * 1.3,
                              textColor=color, alignment=align)

    def p(self, text: str, **kw) -> Paragraph:
        return Paragraph(text, self.style(**kw))

    def visible(self, key: str) -> list[str]:
        return [x["id"] for x in self.cfg[key] if x["visible"]]

    # --- blocks
    def header(self) -> list:
        s, st = self.school, self.cfg["style"]
        text = [self.p(f"<b>{_esc(s['name']) or '&nbsp;'}</b>", size=self.fs + 7, align=TA_CENTER)]
        if s["address"]:
            text.append(self.p(_esc(s["address"]), size=self.fs - 0.5, color=MUTE, align=TA_CENTER))
        logo = None
        if s["logo"] is not None and st["logo_position"] != "none":
            try:
                logo = Image(str(s["logo"]))
                k = min(st["logo_size"] / logo.imageWidth, st["logo_size"] / logo.imageHeight)
                logo.drawWidth, logo.drawHeight = logo.imageWidth * k, logo.imageHeight * k
            except Exception:
                logo = None
        side = st["logo_size"] + 8
        if logo is not None and st["logo_position"] == "center":
            rows, widths = [[logo], [text]], [self.width]
        else:
            rows, widths = [[logo or "", text, ""]], [side, self.width - 2 * side, side]
        t = Table(rows, colWidths=widths)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                               ("LINEBELOW", (0, len(rows) - 1), (-1, len(rows) - 1), 1.2, self.accent),
                               ("BOTTOMPADDING", (0, len(rows) - 1), (-1, len(rows) - 1), 8)]))
        return [t, Spacer(1, 8)]

    def title(self, text: str) -> list:
        return [self.p(f"<b>{_esc(text)}</b>", size=self.fs + 5, align=TA_CENTER, color=self.accent), Spacer(1, 10)]

    def details(self, rows: list[tuple[str, str]]) -> list:
        cells = [[self.p(_esc(k), color=MUTE), self.p(f"<b>{_esc(v) or '–'}</b>")] for k, v in rows]
        data = [cells[i] + (cells[i + 1] if i + 1 < len(cells) else ["", ""]) for i in range(0, len(cells), 2)]
        w = self.width
        t = Table(data, colWidths=[w * 0.17, w * 0.33, w * 0.17, w * 0.33])
        t.setStyle(TableStyle(self._borders(len(data), header=False) + [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                                                       ("TOPPADDING", (0, 0), (-1, -1), 4),
                                                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return [t, Spacer(1, 10)]

    def summary(self, items: list[tuple[str, str]]) -> list:
        if not items:
            return []
        cell = lambda k, v: Paragraph(  # noqa: E731
            f"<font color='#64748B' size='{self.fs - 1}'>{_esc(k)}</font><br/><b><font size='{self.fs + 4}'>{_esc(v)}</font></b>",
            self.style(align=TA_CENTER, leading=self.fs * 1.8))
        t = Table([[cell(k, v) for k, v in items]], colWidths=[self.width / len(items)] * len(items))
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, self.accent), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return [t, Spacer(1, 12)]

    def section_title(self, text: str) -> list:
        return [self.p(f"<b>{_esc(text)}</b>", size=self.fs + 1), Spacer(1, 4)]

    def _borders(self, n_rows: int, header: bool = True, total: bool = False) -> list:
        mode = self.cfg["style"]["borders"]
        if mode == "grid":
            out = [("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE)]
        elif mode == "lines":
            out = [("LINEBELOW", (0, i), (-1, i), 0.4, LINE) for i in range(n_rows)]
        else:
            out = []
        if self.cfg["style"]["zebra"]:
            start, end = (2 if header else 1), n_rows - (1 if total else 0)
            out += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(start, end, 2)]
        return out

    def table(self, head: list[str], rows: list[list], widths: list[float], total: list | None = None,
              aligns: list[int] | None = None) -> Table:
        """aligns: header alignment per column, matching how its values are aligned."""
        aligns = aligns or [TA_LEFT] * len(head)
        data = [[Paragraph(_esc(h), self.style(size=self.fs - 0.5, bold=True, color=colors.white, align=a))
                 for h, a in zip(head, aligns)]] + rows + ([total] if total else [])
        t = Table(data, colWidths=widths, repeatRows=1)
        st = [("BACKGROUND", (0, 0), (-1, 0), self.accent), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        st += self._borders(len(data), total=bool(total))
        if total:
            st += [("BACKGROUND", (0, -1), (-1, -1), TOTAL_BG), ("LINEABOVE", (0, -1), (-1, -1), 1, MUTE)]
        t.setStyle(TableStyle(st))
        return t

    def note(self) -> list:
        n = self.cfg["text"]["note"].strip()
        if not n:
            return []
        t = Table([[self.p(_esc(n), size=self.fs - 0.5)]], colWidths=[self.width])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("BACKGROUND", (0, 0), (-1, -1), ZEBRA),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return [Spacer(1, 6), t, Spacer(1, 6)]

    def remarks(self) -> list:
        t = Table([[self.p(f"<b>{_esc(self.L['remarks'])}</b>")], [""], [""]], colWidths=[self.width], rowHeights=[16, 20, 20])
        t.setStyle(TableStyle([("LINEBELOW", (0, 1), (-1, 2), 0.4, LINE)]))
        return [Spacer(1, 10), t]

    def signatures(self) -> list:
        signers = self.cfg["signers"]
        if not signers:
            return []
        principal = self.school["principal_name"]
        labels = [f"{_esc(s)}<br/><font color='#64748B' size='{self.fs - 1.5}'>{_esc(principal)}</font>"
                  if principal and "principal" in s.lower() else _esc(s) for s in signers]
        w = self.width / len(signers)
        cells = [[Spacer(1, 30), HRFlowable(width="80%", thickness=0.6, color=colors.black, spaceAfter=3),
                  self.p(l, size=self.fs - 0.5, align=TA_CENTER)] for l in labels]
        t = Table([cells], colWidths=[w] * len(signers))
        return [KeepTogether([Spacer(1, 10), t])]

    def grade_scale(self) -> list:
        return [Spacer(1, 8), self.p(f"{_esc(self.L['grade_scale'])}: {GRADE_SCALE_TEXT}", size=self.fs - 1.5, color=MUTE)]

    def render(self, story: list, title: str, doc_label: str) -> bytes:
        buf = io.BytesIO()
        footer = self.cfg["text"]["footer"].strip() or " · ".join(x for x in (self.school["name"], doc_label) if x)
        font, margin, page = self.font, self.margin, self.page

        class FooterCanvas(canvas.Canvas):
            """Footer text and 'Page X of Y' on every page (two passes to know the page count)."""
            def __init__(self, *a: Any, **k: Any) -> None:
                super().__init__(*a, **k)
                self._pages: list[dict[str, Any]] = []

            def showPage(self) -> None:
                self._pages.append(dict(self.__dict__))
                self._startPage()

            def save(self) -> None:
                for state in self._pages:
                    self.__dict__.update(state)
                    self.saveState()
                    self.setFont(font, 7.5)
                    self.setFillColor(MUTE)
                    self.setStrokeColor(LINE)
                    self.line(margin, 30, page[0] - margin, 30)
                    self.drawString(margin, 19, footer[:120])
                    self.drawRightString(page[0] - margin, 19, f"Page {self._pageNumber} of {len(self._pages)}")
                    self.restoreState()
                    super().showPage()
                super().save()

        doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=34, bottomMargin=44,
                                title=title, author=self.school["name"] or "ADEM")
        doc.build(story, canvasmaker=FooterCanvas)
        return buf.getvalue()


# ---------------------------------------------------------------- per-exam student report

SAMPLE_REPORT = {
    "student": {"name": "Aditi Sharma", "roll": "12", "class": "10 – A", "reg": "2026SCI0412"},
    "exam": {"name": "Term 1 Examination", "subject": "Science", "type": "Term 1", "year": "2026-27",
             "date": "2026-09-18", "finalized": "21 Sep 2026"},
    "obtained": 33.5, "maximum": 40.0,
    "questions": [
        {"no": "1", "k": "K1", "co": "CO1", "max": 2, "obtained": 2, "feedback": "Correct definition.", "adjusted": None},
        {"no": "2", "k": "K2", "co": "CO1", "max": 5, "obtained": 3.5, "feedback": "Explains diffusion but misses an example.",
         "adjusted": "Half mark for the labelled diagram"},
        {"no": "3(a)", "k": "K3", "co": "CO2", "max": 3, "obtained": 3, "feedback": "Accurate calculation.", "adjusted": None},
        {"no": "3(b)", "k": "K4", "co": "CO2", "max": 5, "obtained": 4, "feedback": "Good comparison; one point missing.", "adjusted": None},
        {"no": "4", "k": "K2", "co": "CO3", "max": 10, "obtained": 9, "feedback": "Well structured answer.", "adjusted": None},
        {"no": "5", "k": "K6", "co": "CO3", "max": 15, "obtained": 12, "feedback": "Creative design; safety step omitted.", "adjusted": None},
    ],
}


def report_data(db: Session, teacher: Teacher, ev: Evaluation) -> dict:
    exam, student = ev.exam, ev.student
    questions = (db.query(ExamQuestion).filter_by(exam_id=exam.id)
                 .order_by(ExamQuestion.position, ExamQuestion.display_number).all())
    items = {i.exam_question_id: i for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id)}
    reasons: dict[str, str] = {}
    ids = [i.id for i in items.values()]
    if ids:
        for log in (db.query(AuditLog).filter(AuditLog.entity_type == "evaluation_item", AuditLog.entity_id.in_(ids),
                                              AuditLog.action.in_(["marks_changed", "item_approved"]))
                    .order_by(AuditLog.created_at.desc())):
            if log.entity_id not in reasons and log.reason:
                reasons[log.entity_id] = log.reason
    rows = []
    for q in questions:
        it = items.get(q.id)
        fb = ((it.teacher_feedback or it.ai_feedback or "").strip() if it else "")
        rows.append({"no": q.display_number, "k": q.k_level, "co": q.course_outcome, "max": q.max_marks,
                     "obtained": it.final_marks if it else None, "feedback": fb,
                     "adjusted": (reasons.get(it.id) or "") if it and it.teacher_overridden else None,
                     "not_attempted": bool(it and it.status == "MISSING" and it.not_attempted_confirmed)})
    sclass = student.school_class.name if student.school_class else (exam.school_class.name if exam.school_class else "")
    return {
        "student": {"name": student.name, "roll": student.roll_number, "reg": student.registration_number or "",
                    "class": f"{sclass} – {student.section}" if student.section else sclass},
        "exam": {"name": exam.name, "subject": exam.subject.name if exam.subject else "", "type": exam.exam_type,
                 "year": exam.academic_year, "date": exam.exam_date or "",
                 "finalized": ev.finalized_at.strftime("%d %b %Y") if ev.finalized_at else ""},
        "obtained": ev.total_marks or 0.0, "maximum": ev.maximum_marks or 0.0, "questions": rows,
    }


def render_report(data: dict, cfg: dict, school: dict) -> bytes:
    d, L = _Doc(cfg, school), cfg["labels"]
    pct = _pct(data["obtained"], data["maximum"])
    story: list = []
    for sec in d.visible("sections"):
        if sec == "header":
            story += d.header()
        elif sec == "title":
            story += d.title(L["title"])
        elif sec == "student_details":
            s, e = data["student"], data["exam"]
            story += d.details([(L["student"], s["name"]), (L["roll"], s["roll"]), (L["class"], s["class"]), (L["reg"], s["reg"]),
                                (L["exam"], e["name"]), (L["subject"], e["subject"]), (L["exam_type"], e["type"]),
                                (L["year"], e["year"]), (L["date"], e["date"]), (L["finalized"], e["finalized"])])
        elif sec == "summary":
            vals = {"obtained": (L["obtained"], f"{_m(data['obtained'])} / {_m(data['maximum'])}"),
                    "percentage": (L["percentage"], "–" if pct is None else f"{pct:g}%"),
                    "grade": (L["grade"], cbse_grade(pct))}
            story += d.summary([vals[k] for k in d.visible("summary")])
        elif sec == "marks_table":
            cols = d.visible("columns")
            if not cols:
                continue
            fixed = {"qno": 46, "k_level": 62, "max": 40, "obtained": 52}
            widths = [fixed.get(c, 0) for c in cols]
            if "feedback" in cols:
                widths[cols.index("feedback")] = d.width - sum(widths)
            else:
                widths = [w * d.width / sum(widths) for w in widths]
            fb_style = dict(size=d.fs - 1, leading=(d.fs - 1) * 1.3)
            rows = []
            for q in data["questions"]:
                fb = q["feedback"] or ""
                if len(fb) > 220:
                    fb = fb[:217].rstrip() + "…"
                fb = _esc(fb)
                if q.get("adjusted") is not None:
                    note = L["adjusted"] + (f": {q['adjusted']}" if q["adjusted"] else "")
                    fb = (fb + "<br/>" if fb else "") + f"<font color='#B45309'>{_esc(note)}</font>"
                if q.get("not_attempted") and not fb:
                    fb = _esc(L["not_attempted"])
                cell = {"qno": d.p(f"<b>{_esc(q['no'])}</b>"), "k_level": d.p(_esc(K_LEVELS.get(q["k"], q["k"]) if q["k"] else "–")),
                        "max": d.p(_m(q["max"]), align=TA_RIGHT), "obtained": d.p(f"<b>{_m(q['obtained'])}</b>", align=TA_RIGHT),
                        "feedback": d.p(fb, **fb_style)}
                rows.append([cell[c] for c in cols])
            tot = {"qno": d.p(f"<b>{_esc(L['total'])}</b>"), "max": d.p(f"<b>{_m(data['maximum'])}</b>", align=TA_RIGHT),
                   "obtained": d.p(f"<b>{_m(data['obtained'])}</b>", align=TA_RIGHT)}
            story += d.section_title(L["marks_section"])
            right = {"max", "obtained"}
            story += [d.table([L[f"col_{c}"] for c in cols], rows, widths, total=[tot.get(c, "") for c in cols],
                              aligns=[TA_RIGHT if c in right else TA_LEFT for c in cols]), Spacer(1, 10)]
        elif sec == "outcomes":
            qs = [SimpleNamespace(id=str(i), k_level=q["k"], course_outcome=q["co"], max_marks=q["max"])
                  for i, q in enumerate(data["questions"])]
            out = summarize_outcomes(qs, {str(i): q["obtained"] for i, q in enumerate(data["questions"])})
            tables = []
            for title, rows in ((L["by_k"], out["k_levels"]),):
                rows = [r for r in rows if r["key"] != "Untagged"]
                if rows:
                    col = (d.width - 12) / 2
                    body = [[d.p(_esc(r["label"])),
                             d.p(f"{_m(r['scored'])} / {_m(r['max_marks'])}", align=TA_RIGHT),
                             d.p("–" if r["percentage"] is None else f"{r['percentage']:g}%", align=TA_RIGHT)] for r in rows]
                    tables.append(d.table([title, L["col_obtained"], "%"], body, [col * 0.5, col * 0.3, col * 0.2],
                                          aligns=[TA_LEFT, TA_RIGHT, TA_RIGHT]))
            if tables:
                row = Table([tables + [""] * (2 - len(tables))], colWidths=[(d.width - 12) / 2 + 6] * 2)
                row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                story += [row, Spacer(1, 6)]
        elif sec == "note":
            story += d.note()
        elif sec == "remarks":
            story += d.remarks()
        elif sec == "signatures":
            story += d.signatures()
        elif sec == "grade_scale":
            story += d.grade_scale()
    return d.render(story, f"{L['title']} – {data['student']['name']}", L["title"])


def build_evaluation_pdf_report(db: Session, teacher: Teacher, evaluation_id: str) -> tuple[bytes, str]:
    """Report for one finalized evaluation in the teacher's active template. Returns (pdf_bytes, filename)."""
    ev = get_evaluation(db, teacher, evaluation_id)
    if ev.status != "FINALIZED":
        raise err(400, "EVALUATION_NOT_FINALIZED",
                  f"Reports can only be generated for finalized evaluations. Current status is {ev.status}.")
    profile = db.query(SchoolProfile).filter_by(teacher_id=teacher.id).first()
    pdf = render_report(report_data(db, teacher, ev), active_config(db, teacher, "report"), _school(profile))
    return pdf, f"Report_{_clean_name(ev.student.name, ev.student.roll_number, ev.exam.name)}.pdf"


# ---------------------------------------------------------------- term report card

SAMPLE_CARD = {
    "student": {"name": "Aditi Sharma", "roll": "12", "class": "10 – A", "reg": "2026SCI0412"},
    "term": {"exam_type": "Term 1", "year": "2026-27"},
    "subjects": [{"subject": "English", "maximum": 80, "obtained": 68}, {"subject": "Mathematics", "maximum": 80, "obtained": 74.5},
                 {"subject": "Science", "maximum": 80, "obtained": 66}, {"subject": "Social Science", "maximum": 80, "obtained": 59},
                 {"subject": "Hindi", "maximum": 80, "obtained": None}],
    "rank": 3, "ranked": 38,
}


def report_card_terms(db: Session, teacher: Teacher, class_id: str) -> list[dict]:
    """Academic year + exam type combinations of this class that have finalized results."""
    terms: dict[tuple[str, str], dict] = {}
    for e in db.query(Exam).filter_by(teacher_id=teacher.id, class_id=class_id):
        if not db.query(Evaluation).filter_by(exam_id=e.id, status="FINALIZED").first():
            continue
        t = terms.setdefault((e.academic_year, e.exam_type),
                             {"academic_year": e.academic_year, "exam_type": e.exam_type, "subjects": []})
        t["subjects"].append(e.subject.name if e.subject else e.name)
    return sorted(terms.values(), key=lambda t: (t["academic_year"], t["exam_type"]), reverse=True)


def _subject_rows(db: Session, exams: list[Exam], student_id: str) -> list[dict]:
    rows = []
    for e in exams:
        ev = db.query(Evaluation).filter_by(exam_id=e.id, student_id=student_id, status="FINALIZED").first()
        rows.append({"subject": e.subject.name if e.subject else e.name,
                     "maximum": ev.maximum_marks if ev else e.total_marks, "obtained": ev.total_marks if ev else None})
    return rows


def _overall(rows: list[dict]) -> tuple[float, float]:
    done = [r for r in rows if r["obtained"] is not None]
    return sum(r["obtained"] for r in done), sum(r["maximum"] or 0 for r in done)


def card_data(db: Session, teacher: Teacher, class_id: str, academic_year: str, exam_type: str,
              student_id: str | None = None) -> tuple[list[dict], SchoolClass]:
    cls = db.get(SchoolClass, class_id)
    if cls is None or cls.teacher_id != teacher.id:
        raise err(404, "NOT_FOUND", "Class not found.")
    exams = sorted(db.query(Exam).filter_by(teacher_id=teacher.id, class_id=class_id, academic_year=academic_year,
                                             exam_type=exam_type).all(),
                   key=lambda e: ((e.subject.name if e.subject else ""), e.name))
    if not exams:
        raise err(404, "NO_EXAMS", f"No {exam_type} exams for {cls.name} in {academic_year}.")
    everyone = db.query(Student).filter_by(class_id=class_id).all()
    rows = {s.id: _subject_rows(db, exams, s.id) for s in everyone}
    scores = {sid: got / mx for sid, (got, mx) in ((sid, _overall(r)) for sid, r in rows.items()) if mx}
    ordered = sorted(scores.values(), reverse=True)  # standard competition ranking: 1, 2, 2, 4
    if student_id:
        students = [s for s in everyone if s.id == student_id]
        if not students:
            raise err(404, "NOT_FOUND", "Student not found in this class.")
    else:
        students = sorted(everyone, key=lambda s: (s.section or "", s.roll_number.zfill(12)))
        if not students:
            raise err(404, "NO_STUDENTS", f"{cls.name} has no students.")
    cards = [{"student": {"name": s.name, "roll": s.roll_number, "reg": s.registration_number or "",
                          "class": f"{cls.name} – {s.section}" if s.section else cls.name},
              "term": {"exam_type": exam_type, "year": academic_year}, "subjects": rows[s.id],
              "rank": ordered.index(scores[s.id]) + 1 if s.id in scores else None, "ranked": len(scores)}
             for s in students]
    return cards, cls


def render_cards(cards: list[dict], cfg: dict, school: dict) -> bytes:
    d, L = _Doc(cfg, school), cfg["labels"]
    story: list = []
    for n, c in enumerate(cards):
        if n:
            story.append(PageBreak())
        got, mx = _overall(c["subjects"])
        overall = _pct(got, mx)
        for sec in d.visible("sections"):
            if sec == "header":
                story += d.header()
            elif sec == "title":
                story += d.title(f"{L['title']} · {c['term']['exam_type']} · {c['term']['year']}")
            elif sec == "student_details":
                s = c["student"]
                story += d.details([(L["student"], s["name"]), (L["roll"], s["roll"]), (L["class"], s["class"]), (L["reg"], s["reg"])])
            elif sec == "subjects_table":
                cols = d.visible("columns")
                if not cols:
                    continue
                share = {"subject": 0.4, "max": 0.15, "obtained": 0.17, "percent": 0.13, "grade": 0.15}
                total_share = sum(share[x] for x in cols)
                widths = [d.width * share[x] / total_share for x in cols]
                rows = []
                for r in c["subjects"]:
                    p = _pct(r["obtained"], r["maximum"])
                    cell = {"subject": d.p(f"<b>{_esc(r['subject'])}</b>"), "max": d.p(_m(r["maximum"]), align=TA_RIGHT),
                            "obtained": d.p(_m(r["obtained"]) if r["obtained"] is not None
                                            else f"<font color='#64748B'>{_esc(L['not_evaluated'])}</font>", align=TA_RIGHT),
                            "percent": d.p("–" if p is None else f"{p:g}", align=TA_RIGHT),
                            "grade": d.p(f"<b>{cbse_grade(p)}</b>", align=TA_CENTER)}
                    rows.append([cell[x] for x in cols])
                tot = {"subject": d.p(f"<b>{_esc(L['total'])}</b>"), "max": d.p(f"<b>{_m(mx) if mx else '–'}</b>", align=TA_RIGHT),
                       "obtained": d.p(f"<b>{_m(got) if mx else '–'}</b>", align=TA_RIGHT),
                       "percent": d.p(f"<b>{'–' if overall is None else f'{overall:g}'}</b>", align=TA_RIGHT),
                       "grade": d.p(f"<b>{cbse_grade(overall)}</b>", align=TA_CENTER)}
                story += d.section_title(L["subjects_section"])
                align = {"subject": TA_LEFT, "grade": TA_CENTER}
                story += [d.table([L[f"col_{x}"] for x in cols], rows, widths, total=[tot[x] for x in cols],
                                  aligns=[align.get(x, TA_RIGHT) for x in cols]), Spacer(1, 10)]
            elif sec == "summary":
                vals = {"total": (L["total"], f"{_m(got)} / {_m(mx)}" if mx else "–"),
                        "percentage": (L["percentage"], "–" if overall is None else f"{overall:g}%"),
                        "grade": (L["overall_grade"], cbse_grade(overall)),
                        "rank": (L["rank"], f"{c['rank']} of {c['ranked']}" if c.get("rank") else "–")}
                story += d.summary([vals[k] for k in d.visible("summary")])
            elif sec == "note":
                story += d.note()
            elif sec == "remarks":
                story += d.remarks()
            elif sec == "signatures":
                story += d.signatures()
            elif sec == "grade_scale":
                story += d.grade_scale()
    first = cards[0]["term"] if cards else {"exam_type": "", "year": ""}
    return d.render(story, f"{L['title']} – {first['exam_type']} {first['year']}", f"{L['title']} · {first['exam_type']}")


def build_report_cards(db: Session, teacher: Teacher, class_id: str, academic_year: str, exam_type: str,
                       student_id: str | None = None) -> tuple[bytes, str]:
    """One student's report card, or one page per student of the class. Returns (pdf_bytes, filename)."""
    cards, cls = card_data(db, teacher, class_id, academic_year, exam_type, student_id)
    profile = db.query(SchoolProfile).filter_by(teacher_id=teacher.id).first()
    pdf = render_cards(cards, active_config(db, teacher, "report_card"), _school(profile))
    who = _clean_name(cards[0]["student"]["name"], cards[0]["student"]["roll"]) if student_id else _clean_name(cls.name)
    return pdf, f"ReportCard_{who}_{_clean_name(exam_type, academic_year)}.pdf"


def render_preview(kind: str, cfg: dict, profile: SchoolProfile | None) -> bytes:
    """Sample-data PDF for the template editor."""
    school = _school(profile)
    if not school["name"]:
        school["name"] = "Your School Name"
        school["address"] = school["address"] or "School address · set it in Settings"
    return render_report(SAMPLE_REPORT, cfg, school) if kind == "report" else render_cards([SAMPLE_CARD], cfg, school)
