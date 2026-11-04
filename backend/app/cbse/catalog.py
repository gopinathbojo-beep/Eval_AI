"""Reviewed structural profiles derived from the supplied 2026-27 SQP/MS corpus.

No sample question or answer content is used to grade a new uploaded paper.
"""

from __future__ import annotations
from copy import deepcopy
import re

VERSION = "2026-27.1"


def section(key, start, end, marks, each=None, choices=None):
    return {
        "key": key,
        "start": start,
        "end": end,
        "marks": marks,
        "each": each,
        "internal_choices": choices,
    }


def profile(
    grade, code, name, source, total, sections, aliases=(), duration=180, notes=(),
    upload_driven=False,
):
    return {
        "id": f"cbse-{grade}-{code}",
        "version": VERSION,
        "academic_year": "2026-27",
        "class_level": grade,
        "code": code,
        "name": name,
        "source_stem": source,
        "duration_minutes": duration,
        "total_marks": total,
        "question_count": max((s["end"] for s in sections), default=0),
        "sections": sections,
        "upload_driven": upload_driven,
        "aliases": list(aliases),
        "notes": list(notes),
    }


_SCIENCE12 = [
    section("A", 1, 16, 16, 1),
    section("B", 17, 21, 10, 2),
    section("C", 22, 28, 21, 3),
    section("D", 29, 30, 8, 4),
    section("E", 31, 33, 15, 5),
]
_MATH10 = [
    section("A", 1, 20, 20, 1),
    section("B", 21, 25, 10, 2, 2),
    section("C", 26, 31, 18, 3, 2),
    section("D", 32, 35, 20, 5, 2),
    section("E", 36, 38, 12, 4, 3),
]
PROFILES = [
    profile(
        10,
        "165",
        "Computer Applications",
        "ComputerApplication",
        50,
        [
            section("A", 1, 12, 12, 1),
            section("B", 13, 19, 14, 2),
            section("C", 20, 23, 12, 3),
            section("D", 24, 24, 4, 4),
            section("E", 25, 26, 8, 4),
        ],
        ("Computer Application",),
        duration=120,
    ),
    profile(
        10,
        "101",
        "English Communicative",
        "EnglishComm",
        80,
        [
            section("A", 1, 2, 22),
            section("B", 3, 6, 22),
            section("C", 7, 9, 10),
            section("D", 10, 12, 26),
        ],
        notes=(
            "The introduction says three sections but explicitly lists A-D; the actual four-section paper is authoritative.",
        ),
    ),
    profile(
        10,
        "184",
        "English Language and Literature",
        "EnglishL",
        80,
        [section("A", 1, 2, 20), section("B", 3, 5, 20), section("C", 6, 11, 40)],
        ("English Language & Literature", "English Literature"),
    ),
    profile(
        10,
        "002",
        "Hindi Course A",
        "HindiCourseA",
        80,
        [
            section("A", 1, 2, 14),
            section("B", 3, 6, 16),
            section("C", 7, 11, 30),
            section("D", 12, 15, 20),
        ],
        ("Hindi A",),
    ),
    profile(
        10,
        "085",
        "Hindi Course B",
        "HindiCourseB",
        80,
        [
            section("A", 1, 2, 14),
            section("B", 3, 6, 16),
            section("C", 7, 11, 28),
            section("D", 12, 16, 22),
        ],
        ("Hindi B",),
    ),
    profile(
        10,
        "241",
        "Mathematics Basic",
        "MathsBasic",
        80,
        deepcopy(_MATH10),
        ("Maths Basic",),
    ),
    profile(
        10,
        "041",
        "Mathematics Standard",
        "MathsStandard",
        80,
        deepcopy(_MATH10),
        ("Maths Standard",),
    ),
    profile(
        10,
        "086",
        "Science",
        "Science",
        80,
        [section("A", 1, 16, 30), section("B", 17, 29, 25), section("C", 30, 39, 25)],
    ),
    profile(
        10,
        "087",
        "Social Science",
        "SocialScience",
        80,
        [
            section("A", 1, 9, 20),
            section("B", 10, 19, 20),
            section("C", 20, 28, 20),
            section("D", 29, 38, 20),
        ],
        ("SocialScience",),
    ),
    profile(
        10, "006", "Tamil", "Tamil", 80, [], ("தமிழ்",),
        notes=("Question structure, choices and allocations come from the uploaded paper and scheme.",),
        upload_driven=True,
    ),
    profile(
        12,
        "055",
        "Accountancy",
        "Accountancy",
        80,
        [section("A", 1, 26, 60), section("B", 27, 34, 20)],
        notes=(
            "Part B: explicitly select Financial Statements or Computerised Accounting before verification.",
        ),
    ),
    profile(12, "044", "Biology", "Biology", 70, deepcopy(_SCIENCE12)),
    profile(12, "043", "Chemistry", "Chemistry", 70, deepcopy(_SCIENCE12)),
    profile(
        12,
        "083",
        "Computer Science",
        "ComputerScience",
        70,
        [
            section("A", 1, 21, 21, 1),
            section("B", 22, 28, 14, 2),
            section("C", 29, 31, 9, 3),
            section("D", 32, 35, 16, 4),
            section("E", 36, 37, 10, 5),
        ],
        ("ComputerScience",),
    ),
    profile(
        12,
        "301",
        "English Core",
        "EnglishCore",
        80,
        [section("A", 1, 2, 22), section("B", 3, 6, 18), section("C", 7, 13, 40)],
    ),
    profile(
        12,
        "001",
        "English Elective",
        "EnglishElective",
        80,
        [section("A", 1, 3, 20), section("B", 4, 6, 28), section("C", 7, 13, 32)],
    ),
    profile(12, "042", "Physics", "Physics", 70, deepcopy(_SCIENCE12)),
    profile(
        12,
        "028",
        "Political Science",
        "PolSci",
        80,
        [
            section("A", 1, 12, 12, 1),
            section("B", 13, 18, 12, 2),
            section("C", 19, 23, 20, 4, 2),
            section("D", 24, 26, 12, 4),
            section("E", 27, 30, 24, 6, 4),
        ],
        ("PoliticalScience",),
    ),
    # From the 2026-27 SQP general instructions; each pattern adds up to the printed maximum.
    profile(
        12,
        "041",
        "Mathematics",
        "Maths",
        80,
        [
            section("A", 1, 20, 20, 1),
            section("B", 21, 25, 10, 2, 2),
            section("C", 26, 31, 18, 3, 3),
            section("D", 32, 35, 20, 5, 2),
            section("E", 36, 38, 12, 4),
        ],
        ("Maths",),
    ),
    profile(
        12,
        "241",
        "Applied Mathematics",
        "Applied-Maths",
        80,
        [
            section("A", 1, 20, 20, 1),
            section("B", 21, 25, 10, 2, 2),
            section("C", 26, 31, 18, 3, 2),
            section("D", 32, 35, 20, 5, 2),
            section("E", 36, 38, 12, 4),
        ],
        ("Mathematics", "Applied Maths"),
    ),
    profile(12, "045", "Biotechnology", "Biotechnology", 70, deepcopy(_SCIENCE12)),
    profile(
        12,
        "066",
        "Entrepreneurship",
        "Entrepreneurship",
        70,
        [
            section("A", 1, 18, 18, 1),
            section("B", 19, 24, 12, 2),
            section("C", 25, 29, 15, 3),
            section("D", 30, 34, 25, 5),
        ],
    ),
    profile(
        12,
        "029",
        "Geography",
        "Geography",
        70,
        [
            section("A", 1, 17, 17, 1),
            section("B", 18, 19, 6, 3),
            section("C", 20, 23, 12, 3),
            section("D", 24, 28, 25, 5),
            section("E", 29, 30, 10, 5),
        ],
    ),
    profile(
        12,
        "027",
        "History",
        "History",
        80,
        [
            section("A", 1, 21, 21, 1),
            section("B", 22, 27, 18, 3),
            section("C", 28, 30, 24, 8),
            section("D", 31, 33, 12, 4),
            section("E", 34, 34, 5, 5),
        ],
    ),
    profile(
        12,
        "064",
        "Home Science",
        "HomeScience",
        70,
        [section("A", 1, 14, 14, 1), section("B", 15, 25, 26), section("C", 26, 32, 30)],
    ),
    profile(
        12,
        "065",
        "Informatics Practices",
        "InformaticsPractices",
        70,
        [
            section("A", 1, 21, 21, 1),
            section("B", 22, 28, 14, 2),
            section("C", 29, 32, 12, 3),
            section("D", 33, 34, 8, 4),
            section("E", 35, 37, 15, 5),
        ],
    ),
    profile(
        12,
        "039",
        "Sociology",
        "Sociology",
        80,
        [
            section("A", 1, 16, 16, 1),
            section("B", 17, 25, 18, 2),
            section("C", 26, 32, 28, 4),
            section("D", 33, 35, 18, 6),
        ],
    ),
    # The instructions give mark counts but not every question's place: the uploaded paper sets the structure.
    profile(
        12, "054", "Business Studies", "BusinessStudies", 80, [],
        notes=("Question structure, choices and allocations come from the uploaded paper and scheme.",),
        upload_driven=True,
    ),
    profile(
        12, "030", "Economics", "Economics", 80, [],
        notes=("Question structure, choices and allocations come from the uploaded paper and scheme.",),
        upload_driven=True,
    ),
    profile(
        12, "037", "Psychology", "Psychology", 70, [],
        notes=("Question structure, choices and allocations come from the uploaded paper and scheme.",),
        upload_driven=True,
    ),
    profile(
        12, "302", "Hindi", "Hindi", 80, [], ("Hindi Core", "हिन्दी"),
        notes=("Question structure, choices and allocations come from the uploaded paper and scheme.",),
        upload_driven=True,
    ),
    profile(
        12, "106", "Tamil", "Tamil", 80, [], ("தமிழ்",),
        notes=("Question structure, choices and allocations come from the uploaded paper and scheme.",),
        upload_driven=True,
    ),
]

# Whole-question allocations for language papers with independently scored subparts.
_PARENT_MARKS = {
    "101": [12, 10, 3, 4, 7, 8, 3, 4, 3, 8, 10, 8],
    "184": [10, 10, 10, 5, 5, 5, 5, 12, 6, 6, 6],
    "301": [12, 10, 4, 4, 5, 5, 6, 4, 6, 10, 4, 5, 5],
    "001": [12, 4, 4, 8, 15, 5, 12, 2, 3, 5, 2, 3, 5],
    "002": [7, 7, 4, 4, 4, 4, 5, 6, 5, 6, 8, 6, 5, 5, 4],
    "085": [7, 7, 4, 4, 4, 4, 5, 6, 5, 6, 6, 5, 5, 4, 3, 5],
    "086": [1] * 9
    + [2] * 3
    + [3] * 2
    + [4, 5]
    + [1] * 8
    + [2, 3, 3, 4, 5]
    + [1] * 3
    + [2, 2, 3, 3, 3, 4, 5],
    "087": [1] * 4
    + [2, 3, 5, 4, 2]
    + [1] * 6
    + [2, 5, 4, 3]
    + [1] * 4
    + [2, 2, 3, 5, 4]
    + [1] * 6
    + [3, 3, 3, 5],
    "055": [1] * 16 + [3] * 4 + [4] * 2 + [6] * 4 + [1] * 4 + [3] * 2 + [4, 6],
    "064": [1] * 14 + [2] * 7 + [3] * 4 + [4] * 5 + [5] * 2,
}
_LANGUAGE_CHOICES = {
    "101": {5: [(1, 2)], 6: [(1, 2)], 10: [(2, 3)], 11: [(5, 6)], 12: [(1, 2)]},
    "184": {
        3: [(10, 12)],
        4: [(1, 2)],
        5: [(1, 2)],
        6: [(1, 2)],
        7: [(1, 2)],
        8: [(4, 5)],
        9: [(2, 3)],
        10: [(1, 2)],
        11: [(1, 2)],
    },
    "301": {
        3: [(1, 2)],
        4: [(1, 2)],
        5: [(1, 2)],
        6: [(1, 2)],
        7: [(1, 2)],
        8: [(1, 2)],
        9: [(1, 2)],
        10: [(5, 6)],
        11: [(2, 3)],
        12: [(1, 2)],
        13: [(1, 2)],
    },
    "001": {
        4: [(8, 10)],
        5: [(3, 4)],
        6: [(1, 2)],
        7: [(1, 2), (1, 2)],
        **{n: [(1, 2)] for n in range(8, 14)},
    },
}
for _p in PROFILES:
    _p["parent_marks"] = _PARENT_MARKS.get(
        _p["code"],
        [s["each"] for s in _p["sections"] for n in range(s["start"], s["end"] + 1)],
    )
    _p["choice_rules"] = _LANGUAGE_CHOICES.get(_p["code"], {})
    if _p["code"] == "042":
        for _s in _p["sections"]:
            _s["internal_choices"] = {"B": 2, "C": 1, "E": 3}.get(_s["key"])


# Board patterns where each student answers one of two printed branches: the exam must say which one it marks.
BRANCH_OPTIONS = {
    "055": {"key": "accountancy_option", "label": "Part B option",
            "choices": [{"value": "financial", "label": "Analysis of Financial Statements"},
                        {"value": "computerised", "label": "Computerised Accounting"}]},
}


def profile_options(profile_id: str | None) -> list[dict]:
    """The choices a profile needs at exam creation (Create Exam shows one select per entry)."""
    p = get_profile(profile_id)
    return [BRANCH_OPTIONS[p["code"]]] if p and p["code"] in BRANCH_OPTIONS else []


def get_profile(profile_id: str | None):
    return next((deepcopy(p) for p in PROFILES if p["id"] == profile_id), None)


def grade_for(school_class):
    return (
        int(school_class.grade_level)
        if getattr(school_class, "grade_level", None)
        else int(re.search(r"\b(10|12)\b", school_class.name).group(1))
    )


def resolve_subject(subject, grade):
    name = re.sub(r"\s+", " ", subject.name.strip().casefold())
    return next(
        (
            p
            for p in PROFILES
            if p["class_level"] == grade
            and (
                subject.code == p["code"]
                or name in [p["name"].casefold(), *[a.casefold() for a in p["aliases"]]]
            )
        ),
        None,
    )


def expected_section(p, root):
    return next((s for s in p["sections"] if s["start"] <= root <= s["end"]), None)


def creation_data(body, school_class, subject):
    from ..deps import err
    from .routes import candidates

    p = (
        get_profile(body.standard_profile_id)
        if body.standard_profile_id
        else resolve_subject(subject, grade_for(school_class))
    )
    if not p or p["class_level"] != grade_for(school_class):
        raise err(
            400,
            "CBSE_SUBJECT_REQUIRED",
            "Choose a supported CBSE class and exact subject variant.",
        )
    if p["id"] not in {x["id"] for x in candidates(subject, grade_for(school_class))}:
        raise err(
            400,
            "CBSE_SUBJECT_MISMATCH",
            "The profile does not match the selected subject.",
        )
    options = {"accessibility": "standard", **(body.standard_options or {})}
    if options.get("accessibility") not in {"standard", "accessible"}:
        raise err(400, "CBSE_OPTION_REQUIRED", "Select the paper audience.")
    branch = BRANCH_OPTIONS.get(p["code"])
    if branch and options.get(branch["key"]) not in {c["value"] for c in branch["choices"]}:
        raise err(400, "CBSE_OPTION_REQUIRED",
                  f"Choose the {p['name']} {branch['label']}: "
                  + " or ".join(c["label"] for c in branch["choices"]) + ".")
    if (
        (body.total_marks is not None and body.total_marks != p["total_marks"])
        or (
            body.duration_minutes is not None
            and body.duration_minutes != p["duration_minutes"]
        )
        or (body.academic_year is not None and body.academic_year != p["academic_year"])
    ):
        raise err(
            400,
            "CBSE_FIXED_PATTERN",
            "Maximum marks, duration and academic year must match the board profile.",
        )
    return {
        **body.model_dump(),
        "standard_profile_id": p["id"],
        "standard_version": VERSION,
        "standard_options": options,
        "total_marks": p["total_marks"],
        "duration_minutes": p["duration_minutes"],
        "exam_type": "Board pattern",
        "academic_year": p["academic_year"],
    }
