"""CBSE syllabus per class and subject: syllabus.json in the subject's own folder, beside its format.json
(class10/subjects/science/syllabus.json, class12/subjects/tamil/syllabus.json).

    {"units": [{"name": "Chemical Substances", "marks": 25,
                "chapters": ["Chemical Reactions and Equations", "Acids, Bases and Salts"]}]}
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent  # app/cbse


def load(standard: str | int, subject: str) -> dict | None:
    """The syllabus of a class ('10') and subject folder ('science', 'Social Science'); None when none has been added."""
    path = ROOT / f"class{standard}" / "subjects" / subject.strip().lower().replace(" ", "_") / "syllabus.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
