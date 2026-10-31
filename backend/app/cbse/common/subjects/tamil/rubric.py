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

from . import format as tamil_format

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


# Point questions: a part "அ) ..." (bulleted, or a table row "| அ) ... | wrong | right |"), its marks "(1)" at the
# end, the per-answer rule "ஒவ்வொரு சரியான விடைக்கும் ½ மதிப்பெண்", and an answer lead "விடை:" / "விடைகள்:"
_BULLET = re.compile(r"^\s*[•*\-]\s*")
_PART_LINE = re.compile(rf"^\(?([{tamil_format.SUB_LETTERS}])\)\s*(.*)$")
_PART_MARKS = re.compile(r"\s*\(\s*(\d+(?:\.\d+)?|½)\s*\)\s*\.?\s*$")
_PER_ITEM = re.compile(r"ஒவ்வொ\S*.*?(\d+(?:\.\d+)?|½)\s*மதிப்பெண்")
_ANSWER_LEAD = re.compile(r"^(?:மாதிரி\s*)?விடை(?:கள்)?\s*:\s*")
_PAIR = re.compile(r"^(?P<q>.+?)\s+[-–]\s+(?P<a>[^-–]+?)\.?$")  # "உயர்வு - தாழ்வு", "திருக்குறளை இயற்றியவர் - திருவள்ளுவர்."
_EXACT_WORDS = 3  # an expected answer this short is checked word for word
_PART_LABEL = re.compile(r"^\(\s*[ivx]{1,4}\s*\)\s*")


@dataclass
class Criterion:
    text: str
    marks: float | None
    kind: str = "criterion"  # criterion (open questions), exact or meaning (point questions)
    part: str | None = None
    expected: list[str] = field(default_factory=list)


@dataclass
class _Part:
    letter: str
    question: str = ""  # the sub-question the key repeats ("அ) தாய்மொழியின் முக்கியத்துவம் என்ன? (1)")
    answer: str = ""
    marks: float | None = None
    items: list[tuple[str, str | None]] = field(default_factory=list)  # (text, expected answer or None)


@dataclass
class Rubric:
    kind: str
    criteria: list[Criterion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # for the teacher's one-time review

    @property
    def total(self) -> float:
        return sum(c.marks or 0 for c in self.criteria)

    def to_dict(self) -> dict:
        """Stored like the shared rubric (common/rubric.py)."""
        points = [{"id": str(i), "marks": c.marks, "text": c.text, "kind": c.kind, "part": c.part, "expected": c.expected}
                  for i, c in enumerate(self.criteria, 1)]
        return {"kind": self.kind, "points": points, "notes": self.notes, "deductions": [], "problems": self.problems,
                "stated_total": None, "total": self.total}


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


def _key_parts(key_text: str) -> list[_Part]:
    """The key's parts in order, each with its answer, marks and the items it checks ("x - y" pairs, table rows)."""
    parts: list[_Part] = []
    for raw in key_text.splitlines()[1:]:  # the first line is the question's heading
        line = _BULLET.sub("", raw.strip())
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and (m := _PART_LINE.match(cells[0])):  # "| அ) sentence | wrong | right |"
                text = f"{m.group(2)}: {' → '.join(cells[1:])}" if len(cells) > 2 else m.group(2)
                parts.append(_Part(m.group(1), answer=text, items=[(text, cells[-1].strip(" ."))]))
            continue
        marks = None
        if mm := _PART_MARKS.search(line):
            marks, line = _marks(mm.group(1)), line[:mm.start()].strip()
        if m := _PART_LINE.match(line):
            body = m.group(2).strip()
            asks = body.endswith("?")  # the key repeats the sub-question; its answer follows under "விடை:"
            parts.append(_Part(m.group(1), question=body if asks else "", answer="" if asks else body, marks=marks))
        elif parts and (rest := _ANSWER_LEAD.sub("", line)):
            parts[-1].answer = f"{parts[-1].answer} {rest}".strip()
            parts[-1].marks = parts[-1].marks if marks is None else marks
    for p in parts:
        if p.items:
            continue
        # "எதிர்ச்சொற்கள்: உயர்வு - தாழ்வு; நன்மை - தீமை": one item per pair, each expecting its second word
        body = re.sub(r"^[^:;]{1,30}:\s*", "", p.answer) if ";" in p.answer else p.answer
        pairs = [_PAIR.match(s.strip()) for s in body.split(";")]
        if all(pairs) and all(len(m.group("a").split()) <= _EXACT_WORDS for m in pairs):
            p.items = [(f"{m.group('q')} - {m.group('a')}", m.group("a")) for m in pairs]
        else:
            p.items = [(p.answer, None)]
    return parts


def _point(text: str, marks: float | None, part: str | None, expected: str | None) -> Criterion:
    exact = bool(expected) and len(expected.split()) <= _EXACT_WORDS
    return Criterion(text, marks, "exact" if exact else "meaning", part, [expected] if exact else [])


def _point_rubric(rubric: Rubric, key_text: str, crit_lines: list[str], max_marks: float | None) -> Rubric:
    """Marking points of a point question: per-answer marks over the key's items, marked criteria over its parts (in
    order when they match one for one), otherwise the parts' own marks, otherwise the answer as a whole."""
    parts = _key_parts(key_text)
    per_item = next((_marks(m.group(1)) for l in crit_lines if (m := _PER_ITEM.search(l))), None)
    marked = [c for c in map(parse_criterion, crit_lines) if c.marks is not None and not _PER_ITEM.search(c.text)]
    rubric.notes += [l for l in crit_lines if parse_criterion(l).marks is None and not _PER_ITEM.search(l)]
    if per_item is not None:
        if not parts:
            rubric.problems.append("The key gives marks per answer, but lists no answers அ), ஆ), ...")
        rubric.criteria = [_point(t, per_item, p.letter, e) for p in parts for t, e in p.items]
    elif marked and len(marked) == len(parts):
        for c, p in zip(marked, parts):
            rubric.criteria.append(_point(f"{c.text}: {p.answer}", c.marks, p.letter, p.items[0][1] if len(p.items) == 1 else None))
            if p.marks is not None and abs(p.marks - c.marks) > 1e-9:
                rubric.problems.append(f"Part ({p.letter}) has {p.marks:g} marks in the key's answer but {c.marks:g} in its scheme")
    elif marked:
        rubric.criteria = [Criterion(c.text, c.marks, "meaning") for c in marked]
    elif parts and all(p.marks is not None for p in parts):
        rubric.criteria = [_point(p.answer, p.marks, p.letter, p.items[0][1] if len(p.items) == 1 else None) for p in parts]
    elif max_marks:
        # A one-line key is the answer itself: a CBSE part's key "(i) D) ஆசிரியப்பாக்கள்" (its label dropped)
        lines = key_text.splitlines()
        body = _PART_LABEL.sub("", "\n".join(lines[1:] if len(lines) > 1 else lines).strip())
        answer = re.sub(r"\s+", " ", _ANSWER_LEAD.sub("", _BULLET.sub("", body))).strip()
        rubric.criteria = [_point(answer or "Matches the key's answer", max_marks, None, answer)]
        rubric.notes.append("No marking scheme in the key: the answer is graded as a whole")
    if not rubric.criteria:
        rubric.problems.append("No marking scheme in the key and no marks for the question")
    elif max_marks is not None and abs(rubric.total - max_marks) > 1e-9:
        rubric.problems.append(f"Marking points add up to {rubric.total:g}, the question has {max_marks:g} marks")
    return rubric


def build_rubric(question_text: str | None, key_text: str | None, key_criteria: list[str] | None,
                 max_marks: float | None) -> Rubric:
    """The rubric of one question. Open kinds (letter, essay, paragraph) get their criteria and marks; point questions
    get their marking points, exact (fill-ins, word pairs, corrections) or by meaning."""
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
        return _point_rubric(rubric, key_text or "", crit_lines, max_marks)
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
