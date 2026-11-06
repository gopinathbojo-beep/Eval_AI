"""Which extraction issues need the teacher, and which the app has already settled.

A settled issue had a safe default applied when the paper or scheme was read (the first page's reading, the printed
question number, a missing picture left out). It is kept as a note on the question or scheme for
reference but never holds it for review. Everything else (missing marks, a scoring tree that cannot be built,
allocations that do not add up) changes the marks and still needs the teacher."""
import re

_SETTLED = re.compile(
    r"^(?:Page \d+:\s*)?(?:"
    r"Conflicting (?:kind|limit|audience) for "            # part-less or same-shape readings: the first one stands
    r"|Conflicting section labels across pages"             # the first page's section
    r"|Conflicting whole-question marks across pages"       # the marks printed where the question starts
    r"|Conflicting \w+ on page \d+"                         # page metadata (school, set, date): not used in marking
    r"|Conflicting deduction rule "                         # one rule kept per id
    r"|Duplicate part or criterion IDs on this source page" # repeated ids are merged when grading
    r"|Invalid \w+ crop on page"                            # the picture is left out; the text stays
    r"|Could not store \w+ crop on page"
    r"|Model root .* was corrected to printed question"     # already corrected to the printed number
    r"|Removed alternative "                                # already removed
    r"|Text above printed question \S+ continues question"  # already joined to that question
    r"|Repeated whole-question label"                       # a question printed again: an OR alternative, a visually
                                                            # impaired version or the other Part B option
    r")",
    re.I,
)


def settled(issue: str) -> bool:
    return bool(_SETTLED.search(issue or ""))


def split(issues):
    """(needs_teacher, settled_notes)"""
    issues = list(issues or [])
    return [i for i in issues if not settled(i)], [i for i in issues if settled(i)]
