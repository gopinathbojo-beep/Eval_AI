"""The marking rubric of a Tamil question, built from its answer key. Tamil subjects only.

A question is one of four kinds, told by its own wording first, then by its key:
  letter     கடிதம் எழுதுக: graded as a whole on its criteria (கடித வடிவம், உள்ளடக்கம், மொழிநடை)
  essay      கட்டுரை எழுதுக: graded as a whole on its criteria (கருத்துகள், அமைப்பு, மொழிநடை)
  paragraph  "write three or four sentences on the topic" (தலைப்பில் ... வாக்கியங்களில் எழுதுக): like an essay
  points     everything else: parts and marking points, graded point by point against the key

Letters, essays and paragraphs keep the grading they have today; their rubric is the key's criteria, each with its
marks ("கடித வடிவம் – 1 மதிப்பெண்"), which must add up to the question's marks. A key's notes ("குறிப்பு: ...") are
kept apart from its criteria: they guide the grader and carry no marks.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from . import tamil_format

LETTER, ESSAY, PARAGRAPH, POINTS = "letter", "essay", "paragraph", "points"
OPEN_KINDS = (LETTER, ESSAY, PARAGRAPH)

_LETTER = re.compile(r"கடிதம்|கடிதத்தை|மடல்")
_ESSAY = re.compile(r"கட்டுரை")
_PARAGRAPH = re.compile(r"(?:தலைப்பில்|தலைப்பைப்\s*பற்றி).{0,40}(?:வாக்கியங்களில்|வரிகளில்|பத்தி)|பத்தி\s*எழுதுக")
_LETTER_FORMAT = re.compile(r"கடித\s*வடிவ")
# "கடித வடிவம் – 1 மதிப்பெண்.", "1 மதிப்பெண் - கல்வியின் மூலம் ...", "... – 2 மதிப்பெண்கள்."
_MARKS_AFTER = re.compile(r"^(?P<text>.+?)\s*[-–—:]\s*(?P<m>\d+(?:\.\d+)?|½)\s*மதிப்பெண்(?:கள்)?\s*\.?\s*$")
_MARKS_BEFORE = re.compile(r"^(?P<m>\d+(?:\.\d+)?|½)\s*மதிப்பெண்(?:கள்)?\s*[-–—:]\s*(?P<text>.+?)\.?\s*$")
_NOTE = re.compile(r"^\s*(?:குறிப்பு|கவனிக்க)\s*:")


@dataclass
class Criterion:
    text: str
    marks: float | None


@dataclass
class Rubric:
    kind: str
    criteria: list[Criterion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # for the teacher's one-time review


def question_kind(question_text: str | None, key_text: str | None = None) -> str:
    """letter / essay / paragraph / points, from the question's wording (the key's when the question says nothing)."""
    head = "\n".join((question_text or "").splitlines()[:3])
    for text in (head, (key_text or "").partition("\n")[0]):
        if _LETTER.search(text):
            return LETTER
        if _ESSAY.search(text):
            return ESSAY
        if _PARAGRAPH.search(text):
            return PARAGRAPH
    if _LETTER_FORMAT.search(key_text or ""):
        return LETTER
    return POINTS


def _marks(value: str) -> float:
    return 0.5 if value == "½" else float(value)


def parse_criterion(line: str) -> Criterion:
    s = re.sub(r"^\s*[•*\-]\s*", "", line).strip()
    for pat in (_MARKS_AFTER, _MARKS_BEFORE):
        if m := pat.match(s):
            return Criterion(m.group("text").strip(" .–-"), _marks(m.group("m")))
    return Criterion(s.rstrip("."), None)


def _join_notes(lines: list[str]) -> tuple[list[str], list[str]]:
    """(criteria lines, notes): a note runs on over the lines that follow it until a line that states marks."""
    crit, notes = [], []
    in_note = False
    for line in (l.strip() for l in lines if l and l.strip()):
        has_marks = parse_criterion(line).marks is not None
        if _NOTE.match(line):
            notes.append(line)
            in_note = True
        elif in_note and not has_marks:
            notes[-1] = f"{notes[-1]} {line}"
        else:
            in_note = False
            crit.append(line)
    return crit, notes


def build_rubric(question_text: str | None, key_text: str | None, key_criteria: list[str] | None,
                 max_marks: float | None) -> Rubric:
    """The rubric of one question. Open kinds (letter, essay, paragraph) get their criteria and marks; point questions
    are graded as they are today until point rubrics are built."""
    kind = question_kind(question_text, key_text)
    note_lines = [l.strip() for l in (key_text or "").splitlines() if _NOTE.match(l)]
    crit_lines, notes = _join_notes(list(key_criteria or []))
    # A note in the answer text that stops mid-sentence ("... ஏற்ற சரியான,") goes on in the criteria's first unmarked line
    while note_lines and not note_lines[-1].rstrip().endswith((".", "?", "!")):
        rest = next((l for l in crit_lines if parse_criterion(l).marks is None), None)
        if rest is None:
            break
        crit_lines.remove(rest)
        note_lines[-1] = f"{note_lines[-1]} {rest.strip()}"
    rubric = Rubric(kind, notes=[*note_lines, *[n for n in notes if n not in note_lines]])
    if kind not in OPEN_KINDS:
        return rubric
    rubric.criteria = [parse_criterion(l) for l in crit_lines]
    rubric.criteria = [c for c in rubric.criteria if c.text]
    if not rubric.criteria:
        rubric.problems.append("No marking criteria in the key")
    elif any(c.marks is None for c in rubric.criteria):
        rubric.problems.append("A criterion states no marks: " + "; ".join(c.text for c in rubric.criteria if c.marks is None))
    elif max_marks is not None and abs(sum(c.marks for c in rubric.criteria) - max_marks) > 1e-9:
        rubric.problems.append(f"Criteria add up to {sum(c.marks for c in rubric.criteria):g}, the question has {max_marks:g} marks")
    model = re.sub(r"^.*?மாதிரி\s*விடை\s*:?", "", key_text or "", count=1, flags=re.S).strip()
    if kind == LETTER and len(tamil_format.indic_tokens(model)) < 15:
        rubric.problems.append("The key's model letter is missing or almost empty (OCR may have lost it)")
    return rubric
