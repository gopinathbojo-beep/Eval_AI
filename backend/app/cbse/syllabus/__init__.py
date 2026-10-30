"""CBSE syllabus per class and subject, one JSON file each: class10/science.json, class12/english.json ...

    {"units": [{"name": "Chemical Substances", "marks": 25,
                "chapters": ["Chemical Reactions and Equations", "Acids, Bases and Salts"]}]}
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).parent


def load(standard: str | int, subject: str) -> dict | None:
    """The syllabus of a class ('10') and subject ('Science'); None when no file has been added for it."""
    path = ROOT / f"class{standard}" / f"{subject.strip().lower().replace(' ', '_')}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
