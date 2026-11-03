"""Create Exam offers joined subjects ("Hindi", "Mathematics", "English"); the uploaded question paper decides the
exact CBSE paper (Hindi Course A 002 / B 085, Mathematics Standard 041 / Basic 241, ...).

Read from the paper's text layer before its pages are read, so extraction uses the right pattern. A scanned paper
has no text layer and keeps the usual variant chosen at creation."""

import re

from .catalog import get_profile, grade_for
from .routes import candidates


def pick_variant(exam, pages: list[dict]) -> str | None:
    """Switch exam to the variant its question paper names; returns the new profile id, or None if unchanged."""
    if not exam.standard_profile_id or not exam.subject or not exam.school_class:
        return None
    options = candidates(exam.subject, grade_for(exam.school_class))
    if len(options) < 2:
        return None
    text = " ".join(p.get("page_text") or "" for p in pages[:2])
    if not text.strip():
        return None
    folded = re.sub(r"\s+", " ", text).casefold()
    by_code = [p for p in options if re.search(rf"(?<!\d){p['code']}(?!\d)", text)]
    by_name = [p for p in options if p["name"].casefold() in folded]
    found = by_code if len(by_code) == 1 else by_name if len(by_name) == 1 else []
    if not found or found[0]["id"] == exam.standard_profile_id:
        return None
    p = get_profile(found[0]["id"])
    exam.standard_profile_id = p["id"]
    exam.total_marks, exam.duration_minutes = p["total_marks"], p["duration_minutes"]
    exam.standard_validation = None
    return p["id"]
