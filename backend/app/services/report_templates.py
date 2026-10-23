"""Editable layouts for the exam report and the report card.

A template is a JSON config: section order/visibility, table columns, summary items, every visible label,
styling, free text and signature lines. Saved configs are always normalized against the defaults below, so a
template saved by an older version still renders, and unknown keys are dropped.
"""
from __future__ import annotations
import copy
import re
from sqlalchemy.orm import Session
from ..models import ReportTemplate, SchoolProfile, Teacher

KINDS = ("report", "report_card")

_COMMON_LABELS = {
    "student": "Student", "roll": "Roll No.", "class": "Class", "reg": "Reg. No.",
    "total": "Total", "percentage": "Percentage", "grade": "Grade", "remarks": "Remarks",
    "grade_scale": "Grading scale (CBSE)",
}

DEFAULTS: dict[str, dict] = {
    "report": {
        "sections": ["header", "title", "student_details", "summary", "marks_table", "outcomes", "note", "remarks",
                     "signatures", "grade_scale"],
        "columns": ["qno", "k_level", "max", "obtained", "feedback"],
        "summary": ["obtained", "percentage", "grade"],
        "labels": {**_COMMON_LABELS,
                   "title": "Examination Report", "exam": "Examination", "subject": "Subject", "exam_type": "Exam Type",
                   "year": "Academic Year", "date": "Exam Date", "finalized": "Finalized",
                   "obtained": "Marks Obtained", "marks_section": "Question-wise Marks",
                   "col_qno": "Q. No.", "col_k_level": "Level", "col_max": "Max", "col_obtained": "Obtained",
                   "col_feedback": "Feedback", "by_k": "By Knowledge Level",
                   "adjusted": "Adjusted by teacher", "not_attempted": "Not attempted"},
        "signers": ["Subject Teacher", "Principal", "Parent / Guardian"],
    },
    "report_card": {
        "sections": ["header", "title", "student_details", "subjects_table", "summary", "note", "remarks",
                     "signatures", "grade_scale"],
        "columns": ["subject", "max", "obtained", "percent", "grade"],
        "summary": ["total", "percentage", "grade", "rank"],
        "labels": {**_COMMON_LABELS,
                   "title": "Report Card", "subjects_section": "Subject-wise Performance", "col_subject": "Subject",
                   "col_max": "Max Marks", "col_obtained": "Obtained", "col_percent": "%", "col_grade": "Grade",
                   "overall_grade": "Overall Grade", "rank": "Class Rank", "not_evaluated": "Not evaluated"},
        "signers": ["Class Teacher", "Principal", "Parent / Guardian"],
    },
}
_STYLE = {"accent": "#1E3A5F", "font": "default", "font_size": 9.0, "logo_size": 56, "logo_position": "left",
          "borders": "grid", "zebra": True, "paper": "A4"}
_TEXT = {"footer": "", "note": ""}
FONTS = ("default", "helvetica", "times")
LOGO_POSITIONS = ("left", "center", "none")
BORDERS = ("grid", "lines", "none")
PAPERS = ("A4", "Letter")

PRESETS = {
    "classic": {"name": "Classic", "style": {}},
    "modern": {"name": "Modern", "style": {"accent": "#0F766E", "logo_position": "center", "borders": "lines",
                                           "font_size": 9.5}},
    "minimal": {"name": "Minimal", "style": {"accent": "#111827", "borders": "lines", "zebra": False,
                                             "logo_position": "none", "font": "helvetica"}},
}


def _ordered(value, allowed: list[str]) -> list[dict]:
    """[{id, visible}] in the saved order; ids the template doesn't mention are appended (visible)."""
    out, seen = [], set()
    for v in value if isinstance(value, list) else []:
        sid = v.get("id") if isinstance(v, dict) else v
        if sid in allowed and sid not in seen:
            out.append({"id": sid, "visible": bool(v.get("visible", True)) if isinstance(v, dict) else True})
            seen.add(sid)
    return out + [{"id": a, "visible": True} for a in allowed if a not in seen]


def normalize(kind: str, config: dict | None) -> dict:
    if kind not in KINDS:
        raise ValueError(kind)
    d, c = DEFAULTS[kind], config or {}
    style = {**_STYLE, **{k: v for k, v in (c.get("style") or {}).items() if k in _STYLE}}
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(style["accent"])):
        style["accent"] = _STYLE["accent"]
    style["font"] = style["font"] if style["font"] in FONTS else "default"
    style["logo_position"] = style["logo_position"] if style["logo_position"] in LOGO_POSITIONS else "left"
    style["borders"] = style["borders"] if style["borders"] in BORDERS else "grid"
    style["paper"] = style["paper"] if style["paper"] in PAPERS else "A4"
    try:
        style["font_size"] = min(12.0, max(7.0, float(style["font_size"])))
        style["logo_size"] = int(min(110, max(30, float(style["logo_size"]))))
    except (TypeError, ValueError):
        style["font_size"], style["logo_size"] = _STYLE["font_size"], _STYLE["logo_size"]
    style["zebra"] = bool(style["zebra"])
    labels = {k: str(v)[:80] for k, v in {**d["labels"], **(c.get("labels") or {})}.items() if k in d["labels"]}
    signers = [str(s)[:40] for s in (c.get("signers") if isinstance(c.get("signers"), list) else d["signers"]) if str(s).strip()][:4]
    text = {k: str((c.get("text") or {}).get(k, v))[:600] for k, v in _TEXT.items()}
    return {"sections": _ordered(c.get("sections"), d["sections"]), "columns": _ordered(c.get("columns"), d["columns"]),
            "summary": _ordered(c.get("summary"), d["summary"]), "labels": labels, "style": style, "text": text,
            "signers": signers}


def preset_config(kind: str, preset_id: str) -> dict:
    return normalize(kind, {"style": copy.deepcopy(PRESETS[preset_id]["style"])})


def list_presets(kind: str) -> list[dict]:
    return [{"id": f"preset:{pid}", "name": p["name"], "preset": True, "config": preset_config(kind, pid)}
            for pid, p in PRESETS.items()]


def _active_field(kind: str) -> str:
    return "active_report_template" if kind == "report" else "active_card_template"


def active_template_id(profile: SchoolProfile | None, kind: str) -> str:
    return getattr(profile, _active_field(kind)) if profile else "preset:classic"


def resolve(db: Session, teacher: Teacher, kind: str, template_id: str | None) -> dict:
    """Config for a preset id ("preset:modern") or a saved template id; falls back to Classic."""
    if template_id and template_id.startswith("preset:") and template_id[7:] in PRESETS:
        return preset_config(kind, template_id[7:])
    if template_id:
        t = db.get(ReportTemplate, template_id)
        if t and t.teacher_id == teacher.id and t.kind == kind:
            return normalize(kind, t.config)
    return preset_config(kind, "classic")


def active_config(db: Session, teacher: Teacher, kind: str) -> dict:
    profile = db.query(SchoolProfile).filter_by(teacher_id=teacher.id).first()
    return resolve(db, teacher, kind, active_template_id(profile, kind))
