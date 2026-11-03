"""CBSE-style term report card for one student: every subject the student wrote under one exam name ("Term 1").

Layout follows the CBSE school report card: school header, student profile, Scholastic Areas table with marks,
marks out of 100 and grade per subject, result block, class teacher's remarks, signatures, and the 8-point grading
scale. Fields Eval AI does not store (date of birth, parents, attendance, co-scholastic areas) are left out.
Ranks are standard competition ranks over students with every subject finalized: within the section and across all
sections of the class. Remarks are fixed text per grade."""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from ..deps import err
from ..models import Evaluation, Exam, SchoolClass, SchoolProfile, Student, Teacher, Workspace
from ..workspaces import exams_query, owner_id
from .report_generator import BASE_FONT, BOLD_FONT
from .school_reports import _clean_name, _esc, _m, _school
from .student_io import split_class_name

PASS_PERCENT = 33
# CBSE 8-point grading scale for scholastic areas: (lowest marks out of 100, grade)
SCALE = ((91, "A1"), (81, "A2"), (71, "B1"), (61, "B2"), (51, "C1"), (41, "C2"), (33, "D"), (0, "E"))
SCALE_ROWS = (("91 – 100", "A1"), ("81 – 90", "A2"), ("71 – 80", "B1"), ("61 – 70", "B2"), ("51 – 60", "C1"),
              ("41 – 50", "C2"), ("33 – 40", "D"), ("32 & below", "E"))
SUBJECT_REMARKS = {
    "A1": "Outstanding. Keep it up.",
    "A2": "Excellent grasp of concepts.",
    "B1": "Very good. More practice can lift it to the top grade.",
    "B2": "Good. Regular revision will strengthen weaker areas.",
    "C1": "Fair. Needs more practice and revision.",
    "C2": "Average. Must focus on the basics.",
    "D": "Below average. Needs regular practice and guidance.",
    "E": "Needs improvement. Remedial support is required.",
}
OVERALL_REMARKS = {
    "A1": "{name} has shown outstanding performance this term. Keep up the excellent work.",
    "A2": "{name} has done excellent work this term with a strong understanding of all subjects.",
    "B1": "{name} has performed very well. Consistent effort can take {them} to the top grade.",
    "B2": "{name} has done good work. Regular revision will help improve further.",
    "C1": "{name} has made a fair effort. More practice and attention in class are needed.",
    "C2": "{name} needs to work harder and focus on understanding the basics.",
    "D": "{name} needs regular practice and guidance to improve.",
    "E": "{name} needs serious effort and remedial support. Please meet the class teacher.",
}
NAVY = colors.HexColor("#1E3A8A")
LINE = colors.HexColor("#94A3B8")
SHADE = colors.HexColor("#EEF2FF")
MUTE = colors.HexColor("#475569")


def grade_for(percent: float | None) -> str:
    if percent is None:
        return "–"
    marks = int(percent + 0.5)  # marks out of 100, rounded half up
    return next(g for low, g in SCALE if marks >= low)


def rank(scores: dict[str, float]) -> dict[str, int]:
    """Standard competition ranking (1, 2, 2, 4), highest first."""
    ordered = sorted(scores.values(), reverse=True)
    return {k: ordered.index(v) + 1 for k, v in scores.items()}


def _term_exams(db: Session, teacher: Teacher, term: str) -> list[Exam]:
    key = term.strip().casefold()
    return [e for e in exams_query(db, teacher) if e.name.strip().casefold() == key]


def student_terms(db: Session, teacher: Teacher, student: Student) -> list[dict]:
    """Exam names this student has at least one finalized subject in, with how many of the term's subjects are done."""
    by_name: dict[str, dict] = {}
    for e in exams_query(db, teacher).filter(Exam.class_id == student.class_id):
        t = by_name.setdefault(e.name.strip().casefold(), {"term": e.name.strip(), "subjects": 0, "finalized": 0,
                                                          "academic_year": e.academic_year})
        t["subjects"] += 1
        if db.query(Evaluation.id).filter_by(exam_id=e.id, student_id=student.id, status="FINALIZED").first():
            t["finalized"] += 1
    return [t for t in by_name.values() if t["finalized"]]


def _rows(db: Session, exams: list[Exam], student_id: str) -> list[dict]:
    rows = []
    for e in sorted(exams, key=lambda x: x.subject.name if x.subject else x.name):
        ev = db.query(Evaluation).filter_by(exam_id=e.id, student_id=student_id, status="FINALIZED").first()
        mx = (ev.maximum_marks if ev else None) or e.total_marks
        got = ev.total_marks if ev else None
        pct = round(100.0 * got / mx, 2) if got is not None and mx else None
        rows.append({"subject": e.subject.name if e.subject else e.name, "maximum": mx, "obtained": got,
                     "percent": pct, "grade": grade_for(pct), "remark": SUBJECT_REMARKS.get(grade_for(pct), "")})
    return rows


def _overall(rows: list[dict]) -> float | None:
    """Percentage over all subjects, or None until every subject is finalized."""
    if not rows or any(r["obtained"] is None for r in rows):
        return None
    mx = sum(r["maximum"] or 0 for r in rows)
    return round(100.0 * sum(r["obtained"] for r in rows) / mx, 2) if mx else None


def card_data(db: Session, teacher: Teacher, student_id: str, term: str) -> dict:
    student = db.get(Student, student_id)
    exams = _term_exams(db, teacher, term)
    if student is None or not exams:
        raise err(404, "NOT_FOUND", "No exams with this name for the student.")
    cls = db.get(SchoolClass, student.class_id)
    grade_level, section = split_class_name(cls.name)
    own = [e for e in exams if e.class_id == cls.id]
    if not own:
        raise err(404, "NOT_FOUND", f"{cls.name} has no exam named {term}.")
    # every student of every section of this class who wrote this term, for the ranks
    peers: dict[str, tuple[str, float | None]] = {}
    for e in exams:
        ecls = e.school_class
        if not ecls or split_class_name(ecls.name)[0] != grade_level:
            continue
        sec_exams = [x for x in exams if x.class_id == ecls.id]
        for s in db.query(Student).filter_by(class_id=ecls.id):
            if s.id not in peers:
                peers[s.id] = (ecls.id, _overall(_rows(db, sec_exams, s.id)))
    done = {sid: pct for sid, (_, pct) in peers.items() if pct is not None}
    section_done = {sid: pct for sid, pct in done.items() if peers[sid][0] == cls.id}
    rows = _rows(db, own, student.id)
    overall = _overall(rows)
    failed = [r["subject"] for r in rows if r["percent"] is not None and r["percent"] < PASS_PERCENT]
    if overall is None:
        result = "RESULT AWAITED"
    elif not failed:
        result = "PASS"
    else:
        result = "COMPARTMENT" if len(failed) <= 2 else "ESSENTIAL REPEAT"
    overall_grade = grade_for(overall)
    ws = db.get(Workspace, teacher.workspace_id) if teacher.workspace_id else None
    owner = db.get(Teacher, ws.owner_id) if ws else teacher
    first = student.name.split()[0] if student.name.split() else student.name
    return {
        "student": {"name": student.name, "roll": student.roll_number, "class": grade_level,
                    "section": section or student.section or "", "reg": student.registration_number or ""},
        "term": own[0].name.strip(), "year": own[0].academic_year,
        "rows": rows, "overall": overall, "overall_grade": overall_grade, "result": result, "failed": failed,
        "total_obtained": sum(r["obtained"] or 0 for r in rows), "total_maximum": sum(r["maximum"] or 0 for r in rows),
        "section_rank": rank(section_done).get(student.id), "section_ranked": len(section_done),
        "class_rank": rank(done).get(student.id), "class_ranked": len(done),
        "remark": OVERALL_REMARKS[overall_grade].format(name=first, them="them") if overall is not None else
                  "The result will be complete once every subject is evaluated.",
        "affiliation": ((owner.profile or {}).get("affiliation_number") or "").strip() if owner else "",
    }


# ---------------------------------------------------------------- rendering

def _st(size=9.5, bold=False, color=colors.black, align=TA_LEFT) -> ParagraphStyle:
    return ParagraphStyle("s", fontName=BOLD_FONT if bold else BASE_FONT, fontSize=size, leading=size * 1.3,
                          textColor=color, alignment=align)


def _p(text: str, **kw) -> Paragraph:
    return Paragraph(text, _st(**kw))


MARGIN = 36


def render(cards: dict | list[dict], school: dict) -> bytes:
    """One framed A4 page per card."""
    cards = [cards] if isinstance(cards, dict) else cards
    buf = io.BytesIO()
    page_w, page_h = A4

    def border(canvas, _doc):  # CBSE cards carry a framed page
        canvas.saveState()
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(2)
        canvas.rect(18, 18, page_w - 36, page_h - 36)
        canvas.setLineWidth(0.6)
        canvas.rect(22, 22, page_w - 44, page_h - 44)
        canvas.restoreState()

    story: list = []
    for n, card in enumerate(cards):
        if n:
            story.append(PageBreak())
        story += _card_story(card, school, page_w - 2 * MARGIN)
    first = cards[0]
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=34, bottomMargin=34,
                            title=f"Report Card – {first['term']}" + ("" if len(cards) > 1 else f" – {first['student']['name']}"),
                            author=school["name"] or "Eval AI")
    doc.build(story, onFirstPage=border, onLaterPages=border)
    return buf.getvalue()


def _card_story(card: dict, school: dict, width: float) -> list:
    story: list = []
    # header: logo, school name, address, affiliation
    head = [_p(f"<b>{_esc(school['name']) or '&nbsp;'}</b>", size=17, color=NAVY, align=TA_CENTER)]
    if school["address"]:
        head.append(_p(_esc(school["address"]), size=9, color=MUTE, align=TA_CENTER))
    if card["affiliation"]:
        head.append(_p(f"Affiliated to CBSE, New Delhi · Affiliation No. {_esc(card['affiliation'])}", size=9,
                       color=MUTE, align=TA_CENTER))
    logo = ""
    if school["logo"] is not None:
        try:
            logo = Image(str(school["logo"]))
            k = 54 / logo.imageHeight
            logo.drawWidth, logo.drawHeight = min(logo.imageWidth * k, 80), 54
        except Exception:
            logo = ""
    t = Table([[logo, head, ""]], colWidths=[86, width - 172, 86])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story += [t, Spacer(1, 8)]

    bar = Table([[_p("<b>REPORT CARD</b>", size=13, color=colors.white, align=TA_CENTER)],
                 [_p(f"Academic Session: {_esc(card['year'])} &nbsp;·&nbsp; {_esc(card['term'])}", size=9.5,
                     color=colors.white, align=TA_CENTER)]], colWidths=[width])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("TOPPADDING", (0, 0), (-1, -1), 4),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [bar, Spacer(1, 10)]

    # student profile
    s = card["student"]
    info = [[_p("Student's Name", color=MUTE), _p(f"<b>{_esc(s['name'])}</b>"),
             _p("Roll No.", color=MUTE), _p(f"<b>{_esc(s['roll'])}</b>")],
            [_p("Class", color=MUTE), _p(f"<b>{_esc(s['class'])}</b>"),
             _p("Section", color=MUTE), _p(f"<b>{_esc(s['section']) or '–'}</b>")]]
    if s["reg"]:
        info.append([_p("Registration No.", color=MUTE), _p(f"<b>{_esc(s['reg'])}</b>"), "", ""])
    t = Table(info, colWidths=[width * 0.2, width * 0.38, width * 0.14, width * 0.28])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, NAVY), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [t, Spacer(1, 12)]

    # Part 1: scholastic areas
    story += [_p("<b>Part 1: Scholastic Areas</b>", size=10.5, color=NAVY), Spacer(1, 4)]
    hdr = ["S.No.", "Subject", "Max. Marks", "Marks Obtained", "Marks (out of 100)", "Grade", "Remarks"]
    data = [[_p(f"<b>{h}</b>", size=8.5, color=colors.white, align=TA_CENTER) for h in hdr]]
    for i, r in enumerate(card["rows"], 1):
        data.append([_p(str(i), align=TA_CENTER), _p(f"<b>{_esc(r['subject'])}</b>"),
                     _p(_m(r["maximum"]), align=TA_CENTER),
                     _p(_m(r["obtained"]) if r["obtained"] is not None else "Awaited", align=TA_CENTER),
                     _p("–" if r["percent"] is None else str(int(r["percent"] + 0.5)), align=TA_CENTER),
                     _p(f"<b>{r['grade']}</b>", align=TA_CENTER), _p(_esc(r["remark"]), size=8)])
    overall = card["overall"]
    data.append(["", _p("<b>Grand Total</b>"), _p(f"<b>{_m(card['total_maximum'])}</b>", align=TA_CENTER),
                 _p(f"<b>{_m(card['total_obtained']) if overall is not None else '–'}</b>", align=TA_CENTER),
                 _p(f"<b>{'–' if overall is None else f'{overall:g}%'}</b>", align=TA_CENTER),
                 _p(f"<b>{card['overall_grade']}</b>", align=TA_CENTER), ""])
    t = Table(data, colWidths=[w * width for w in (0.07, 0.22, 0.1, 0.12, 0.12, 0.08, 0.29)], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
                           ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("BACKGROUND", (0, -1), (-1, -1), SHADE), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 12)]

    # result block
    def cell(label: str, value: str) -> Paragraph:
        return Paragraph(f"<font color='#475569' size='8'>{_esc(label)}</font><br/><b><font size='12'>{_esc(value)}</font></b>",
                         _st(align=TA_CENTER))
    rank_text = lambda r, n: f"{r} of {n}" if r else "–"  # noqa: E731
    items = [("Percentage", "–" if overall is None else f"{overall:g}%"), ("Overall Grade", card["overall_grade"]),
             ("Rank in Section", rank_text(card["section_rank"], card["section_ranked"])),
             ("Rank in Class", rank_text(card["class_rank"], card["class_ranked"])), ("Result", card["result"])]
    t = Table([[cell(k, v) for k, v in items]], colWidths=[width / len(items)] * len(items))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, NAVY), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [t]
    if card["failed"]:
        story += [Spacer(1, 4), _p(f"Below the pass mark ({PASS_PERCENT}%) in: {_esc(', '.join(card['failed']))}",
                                   size=8.5, color=colors.HexColor("#B91C1C"))]
    story += [Spacer(1, 12)]

    # class teacher's remarks
    t = Table([[_p("<b>Class Teacher's Remarks</b>", color=NAVY)], [_p(_esc(card["remark"]))]], colWidths=[width])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, NAVY), ("LINEBELOW", (0, 0), (-1, 0), 0.4, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [t, Spacer(1, 34)]

    # signatures
    principal = school["principal_name"]
    names = ["Class Teacher", "Principal" + (f"<br/><font size='7.5' color='#475569'>{_esc(principal)}</font>" if principal else ""),
             "Parent / Guardian"]
    t = Table([[_p("_" * 26, align=TA_CENTER)] * 3, [_p(n, size=9, align=TA_CENTER) for n in names]],
              colWidths=[width / 3] * 3)
    story += [t, Spacer(1, 14)]

    # grading scale
    story += [_p("<b>Grading Scale for Scholastic Areas</b> (grades are awarded on an 8-point grading scale)",
                 size=8.5, color=NAVY), Spacer(1, 3)]
    scale = [[_p("<b>Marks Range</b>", size=8, align=TA_CENTER)] + [_p(r, size=8, align=TA_CENTER) for r, _ in SCALE_ROWS],
             [_p("<b>Grade</b>", size=8, align=TA_CENTER)] + [_p(g, size=8, align=TA_CENTER) for _, g in SCALE_ROWS]]
    t = Table(scale, colWidths=[width * 0.12] + [width * 0.11] * 8)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                           ("BACKGROUND", (0, 0), (0, -1), SHADE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [t, Spacer(1, 6),
              _p(f"E: Needs improvement. Pass mark: {PASS_PERCENT}% in each subject. Date of issue: {date.today().strftime('%d %b %Y')}",
                 size=7.5, color=MUTE, align=TA_RIGHT)]

    return story


def class_terms(db: Session, teacher: Teacher, class_id: str) -> list[dict]:
    """Exam names of this class with at least one finalized sheet: the terms a report card can be made for."""
    by_name: dict[str, dict] = {}
    for e in exams_query(db, teacher).filter(Exam.class_id == class_id):
        if not db.query(Evaluation.id).filter_by(exam_id=e.id, status="FINALIZED").first():
            continue
        t = by_name.setdefault(e.name.strip().casefold(), {"term": e.name.strip(), "academic_year": e.academic_year,
                                                          "exam_type": e.name.strip(), "subjects": []})
        t["subjects"].append(e.subject.name if e.subject else e.name)
    return list(by_name.values())


def build_class(db: Session, teacher: Teacher, class_id: str, term: str) -> tuple[bytes, str]:
    """Every student of the class with at least one finalized subject in the term, one card each, roll order."""
    cls = db.get(SchoolClass, class_id)
    exams = [e for e in _term_exams(db, teacher, term) if e.class_id == class_id]
    if cls is None or not exams:
        raise err(404, "NOT_FOUND", f"No exams named {term} for this class.")
    written = {sid for (sid,) in db.query(Evaluation.student_id).filter(
        Evaluation.exam_id.in_([e.id for e in exams]), Evaluation.status == "FINALIZED")}
    students = sorted((s for s in db.query(Student).filter_by(class_id=class_id) if s.id in written),
                      key=lambda s: s.roll_number.zfill(12))
    if not students:
        raise err(404, "NO_RESULTS", "No finalized results for this term yet.")
    profile = db.query(SchoolProfile).filter_by(teacher_id=owner_id(db, teacher)).first()
    pdf = render([card_data(db, teacher, s.id, term) for s in students], _school(profile))
    return pdf, f"ReportCards_{_clean_name(cls.name, exams[0].name)}.pdf"


def build(db: Session, teacher: Teacher, student_id: str, term: str) -> tuple[bytes, str]:
    card = card_data(db, teacher, student_id, term)
    profile = db.query(SchoolProfile).filter_by(teacher_id=owner_id(db, teacher)).first()
    pdf = render(card, _school(profile))
    return pdf, f"ReportCard_{_clean_name(card['student']['name'], card['student']['roll'], card['term'])}.pdf"
