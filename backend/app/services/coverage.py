"""Answer coverage: did every question the student had to answer come out of the sheet?

The question paper says how many questions a student answers: every question once, an either/or group ("11 A OR
11 B", choice_group) once, and a section that says "answer any N" N times. The sheet says which of them have an
answer. Before a question is reported as not found, its printed number is looked for inside the other answers: "12>"
on a line in the middle of Q11's answer means two answers were read as one, and they are split there.

Nothing here holds a sheet for review (a student may skip a question); the result is shown on the sheet.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import StudentAnswer


def units(qs) -> list[dict]:
    """What a student must answer: [{"label", "questions": [...], "need": n}]"""
    out, groups, any_sections = [], defaultdict(list), defaultdict(list)
    for q in qs:
        if q.answer_any and not q.compulsory:
            any_sections[(q.section or "", q.answer_any)].append(q)
        elif q.choice_group:
            groups[q.choice_group].append(q)
        else:
            out.append({"label": f"Q{q.display_number}", "questions": [q], "need": 1, "pos": q.position or 0})
    for group, members in groups.items():
        names = " or ".join(f"Q{m.display_number}" for m in members)
        out.append({"label": names, "questions": members, "need": 1, "pos": min(m.position or 0 for m in members)})
    for (section, n), members in any_sections.items():
        label = f"any {n} of Q{members[0].display_number}-Q{members[-1].display_number}"
        out.append({"label": label, "questions": members, "need": min(n, len(members)),
                    "pos": min(m.position or 0 for m in members)})
    return sorted(out, key=lambda u: u["pos"])


def coverage(db: Session, ev, qs) -> dict:
    """{"required": n, "answered": m, "missing": ["Q5", "Q11 or Q12", ...]}"""
    answered = {a.exam_question_id for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id)
                if a.exam_question_id and a.status != "IGNORED"}
    required = found = 0
    missing = []
    for u in units(qs):
        got = min(u["need"], sum(1 for q in u["questions"] if q.id in answered))
        required += u["need"]
        found += got
        if got < u["need"]:
            missing.append(u["label"] if u["need"] == 1 else f"{u['need'] - got} more ({u['label']})")
    return {"required": required, "answered": found, "missing": missing}


def _label_line(number: str) -> re.Pattern:
    """A line opening with this question's number as a student writes it: "12>", "12)", "12.", "Q12", "12,"."""
    return re.compile(rf"^\s*(?:Q\.?\s*|Question\s*)?{re.escape(number)}\s*(?:[>).:,\-]|\s+[A-Za-z(])", re.I)


def split_merged(db: Session, ev, qs) -> int:
    """Answers read as one: a question with no answer whose printed number opens a line inside another answer.
    That line and what follows become that question's answer. Returns how many were split off."""
    answered = {a.exam_question_id for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id)
                if a.exam_question_id and a.status != "IGNORED"}
    wanted = [q for q in qs if q.id not in answered and (q.normalized_number or "").strip()]
    if not wanted:
        return 0
    rows = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    split = 0
    for q in wanted:
        pattern = _label_line(q.normalized_number)
        for a in rows:
            if a.mapping_confirmed or a.status == "IGNORED":
                continue
            lines = (a.answer_text or "").splitlines()
            at = next((i for i, ln in enumerate(lines) if i > 0 and pattern.match(ln)), None)
            if at is None:
                continue
            head, tail = "\n".join(lines[:at]).strip(), "\n".join(lines[at:]).strip()
            if not head or not tail:
                continue
            a.answer_text = head
            piece = StudentAnswer(evaluation_id=ev.id, raw_question_number=f"Q{q.normalized_number}",
                                  normalized_number=q.normalized_number, raw_ocr_text=tail, answer_text=tail,
                                  page_number=a.page_number, bbox=a.bbox, crop_file=a.crop_file,
                                  ocr_confidence=a.ocr_confidence, position=a.position,
                                  mapping_note=f"Split from the answer above: Q{q.normalized_number} starts there")
            db.add(piece)
            rows.insert(rows.index(a) + 1, piece)
            split += 1
            break
    if split:
        for n, a in enumerate(rows, start=1):  # keep the sheet order
            a.position = n
        db.flush()
    return split
