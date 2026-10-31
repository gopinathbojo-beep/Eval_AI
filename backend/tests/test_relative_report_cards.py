"""Saved report templates from before K levels were removed. Report-card grades (the CBSE 9-point grades) are
tested in test_school_reports.py."""
from app.services.report_templates import normalize


def test_legacy_templates_drop_k_level_and_outcomes():
    template = normalize("report", {"columns": ["qno", "k_level", "max", "obtained"], "sections": ["header", "outcomes", "marks_table"]})
    assert "k_level" not in [c["id"] for c in template["columns"]]
    assert "outcomes" not in [s["id"] for s in template["sections"]]
