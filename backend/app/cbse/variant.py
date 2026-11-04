"""Create Exam offers joined subjects ("Hindi", "Mathematics", "English"); the uploaded question paper decides the
exact CBSE paper (Hindi Course A 002 / B 085, Mathematics Standard 041 / Basic 241, ...).

Read from the paper's text layer before its pages are read, so extraction uses the right pattern. A scanned paper
has no text layer and keeps the usual variant chosen at creation."""

import re

from .catalog import get_profile, grade_for
from .routes import candidates


def adopt_printed_profile(exam, pages):
    """Recognise a legacy exam's explicitly identified CBSE sample paper.

    Subject/class matches and a printed subject code are required; question
    counts alone cannot turn an unrelated school paper into a board paper.
    """
    if exam.standard_profile_id or not exam.subject or not exam.school_class:
        return None
    text = " ".join(p.get("page_text") or "" for p in pages[:2])
    if not re.search(r"sample\s+question\s+paper", text, re.I):
        return None
    try:
        grade = grade_for(exam.school_class)
    except (ValueError, AttributeError, TypeError):
        return None
    roman = {10: "X", 12: "XII"}.get(grade)
    if not roman or not re.search(rf"\bclass\s*[-:\u2013]?\s*(?:{grade}|{roman})\b", text, re.I):
        return None
    found = [p for p in candidates(exam.subject, grade)
             if re.search(rf"(?:\(\s*{p['code']}\s*\)|(?:subject\s+code|code)\s*[:\-]?\s*{p['code']}\b)", text, re.I)]
    if len(found) != 1:
        return None
    from .catalog import VERSION, BRANCH_OPTIONS
    profile = found[0]
    # Profiles requiring a reviewed branch need an explicit existing selection.
    branch = BRANCH_OPTIONS.get(profile["code"])
    options = {"accessibility": "standard", **(exam.standard_options or {})}
    if branch and options.get(branch["key"]) not in {c["value"] for c in branch["choices"]}:
        return None
    exam.standard_profile_id = profile["id"]
    exam.standard_version = VERSION
    exam.standard_options = options
    exam.standard_validation = None
    return profile["id"]


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
