"""Course outcomes (CO1, CO2, ...) for questions, plus marks summaries per outcome."""
from __future__ import annotations
import re


def normalize_course_outcome(v: str | None) -> str | None:
    s = re.sub(r"\s+", "", (v or "")).upper()
    if not s:
        return None
    if s.isdigit():
        s = f"CO{s}"
    return s[:20]


def summarize(questions, marks_by_question: dict[str, float | None]) -> dict:
    """Scored vs maximum marks grouped by course outcome (questions without a tag are 'Untagged')."""
    rows: dict[str, dict] = {}
    for q in questions:
        k = q.course_outcome or "Untagged"
        r = rows.setdefault(k, {"key": k, "questions": 0, "max_marks": 0.0, "scored": 0.0})
        r["questions"] += 1
        r["max_marks"] += q.max_marks or 0.0
        r["scored"] += marks_by_question.get(q.id) or 0.0
    out = []
    for k in sorted(k for k in rows if k != "Untagged") + ["Untagged"]:
        if k in rows:
            r = rows[k]
            r["label"] = k
            r["percentage"] = round(100.0 * r["scored"] / r["max_marks"], 1) if r["max_marks"] else None
            out.append(r)
    return {"course_outcomes": out}
