"""CBSE 9-point grading: grades by rank among the students who passed, not by fixed percentage bands.

The passed students are put in rank order and split into eighths: A1 is the top 1/8th, then A2, B1, B2, C1, C2, D1,
D2. A student below the pass mark gets E (Essential Repeat). Students with the same score get the same grade; when
an eighth's boundary falls inside a group of tied students, the whole group goes with the eighth that holds the
larger part of it (an even split goes up).

The board grades this way only above 500 passed candidates; the school grades each exam's own students, so each
class (each section is its own class) is ranked on its own.
"""
from __future__ import annotations
import math
from typing import Hashable, TypeVar

K = TypeVar("K", bound=Hashable)

GRADES = ("A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2")
FAIL = "E"
PASS_PERCENT = 33
SCALE_TEXT = ("A1, A2, B1, B2, C1, C2, D1, D2: each 1/8th of the passed students in rank order · "
              f"E: Essential Repeat (below {PASS_PERCENT}%)")


def is_pass(percentage: float) -> bool:
    return math.floor(percentage + 0.5) >= PASS_PERCENT  # 32.5% counts as 33 (round() would give 32)


def grades(percentages: dict[K, float | None]) -> dict[K, str]:
    """Each student's grade among this group; "–" for a student without a percentage."""
    out = {k: "–" if p is None else FAIL for k, p in percentages.items()}
    passed = {k: p for k, p in percentages.items() if p is not None and is_pass(p)}
    pos = 0
    for score in sorted(set(passed.values()), reverse=True):
        tied = [k for k, p in passed.items() if p == score]
        eighths = [8 * i // len(passed) for i in range(pos, pos + len(tied))]
        best = max(set(eighths), key=lambda e: (eighths.count(e), -e))
        out.update({k: GRADES[best] for k in tied})
        pos += len(tied)
    return out
