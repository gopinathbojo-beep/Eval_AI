"""A question's marking rubric, built from its answer key: the marking points, each with its marks and how it is
checked. Shared by every subject whose keys are written in English (CBSE-style and set-style keys).

Key layouts it reads:
  CBSE   "• Marking Scheme:" then "1.5 Marks: Content explaining ...", "1 Mark per correct ... pair.",
         "(Deduct ½ mark for major grammatical errors)", "Marking Scheme (5 Marks Total):"
  Set    "KEYWORD MARKING SCHEME / Marks Awarded for" then "1.0 Correct identity.", "0.5 Correct substitution."

Each point gets a kind, which decides how it is graded later:
  number     a final value the student must reach ("answer 1030301", "obtaining 20 days", "(40 m²)")
  unit       an SI unit ("SI unit (kJ/kg)")
  equation   a word or chemical equation ("Correct word equation for (a)")
  exact      one right word ("Correct preposition choice (since)", "Correct word identification for (c)")
  meaning    the idea must be there in the student's own words (definitions, explanations, method steps)
  criterion  a writing task's band (Format / Content / Expression of a notice, letter, diary, essay)

Problems found here (points that do not add up to the question's marks, a part with no points, a point with no marks)
go to the teacher's one-time rubric review.
"""
from __future__ import annotations
import re
from dataclasses import asdict, dataclass, field

POINTS, OPEN = "points", "open"

# A writing task graded as a whole on its bands (format, content, expression), not point by point
_WRITING = re.compile(r"\b(?:notice|diary(?:\s+entry)?|letter|essay|paragraph|story|speech|report|article|"
                      r"message|e-?mail|dialogue|debate|poster|advertisement|invitation|composition)\b", re.I)
_WRITING_VERB = re.compile(r"\b(?:write|draft|compose|prepare)\b", re.I)

_MARKS = r"(?P<m>\d+(?:\.\d+)?|½|¼|¾)"
# "1.5 Marks: text", "1 Mark - text", "2 Marks (½ each): text"
_CBSE_POINT = re.compile(rf"^{_MARKS}\s*Marks?\b\s*(?:\((?P<note>[^)]*)\))?\s*[:\-–—]\s*(?P<text>.+)$", re.I)
# "1 Mark per correct identification and correction pair."
_PER_ITEM = re.compile(rf"^{_MARKS}\s*Marks?\s+(?:per|for\s+each|each\s+for)\s+(?P<text>.+)$", re.I)
# "1.0 Correct identity." (set keys: marks then text, no "Mark" word; needs the decimal so "1. Cornea" is no point)
_SET_POINT = re.compile(r"^(?P<m>\d+\.\d+)\s*(?P<text>[A-Za-z(\[].+)$")
_SCHEME_HEAD = re.compile(r"^(?:keyword\s+)?marking\s+scheme\b(?:\s*\((?P<total>\d+(?:\.\d+)?)\s*marks?\s*total\))?", re.I)
_TABLE_HEAD = re.compile(r"^marks\s*awarded\s*for\b", re.I)
_DEDUCT = re.compile(r"^\(?\s*deduct\b.*", re.I)
_BULLET = re.compile(r"^\s*(?:[•▪*\-–]|o(?=\s|$))[\s•▪*\-–]*")  # "o" is a bullet only on its own: not "otherwise"
_PART_REF = re.compile(r"\(\s*([a-h]|i{1,3}|iv|v)\s*\)")
_PART_LINE = re.compile(r"^\(\s*([a-h])\s*\)\s*(.*)$")
_TABLE_ROW = re.compile(r"^\|\s*\(\s*([a-h])\s*\)\s*\|(.*)\|\s*$")  # "|(a) | habits | habit |"
_NUMBER = re.compile(r"(?<![\w.])(?:Rs\.?\s*)?-?\d[\d,]*(?:\.\d+)?(?![\w])")
_NUMBER_WORDS = re.compile(r"\b(?:answer|obtain(?:ing|ed)?|final|calculat\w*|value|result|get(?:ting)?|days?|computation)\b", re.I)
_UNIT_WORDS = re.compile(r"\bS\.?I\.?\s*units?\b", re.I)
_EQUATION_WORDS = re.compile(r"\bequations?\b", re.I)
_REACTION_WORDS = re.compile(r"\b(?:formula|balanced|product)\b", re.I)  # an equation point when the answer is a reaction
_ARROW = re.compile(r"→|->|⟶")
_SECTION = re.compile(r"^\s*(?:(?:SECTION|PART)\s+[A-Z0-9IVX]+\b|[A-Z]{3,}(?:\s+[A-Z]{3,})+\s*$)")  # or "FINAL STRUCTURE"
# the key's own heading states the question's marks: "Q3. Sum of Cubes in a Range (3 Marks)"
_HEADING_MARKS = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*marks?\s*\)\s*$", re.I)
# a value the point names: "Correct n = 9", "Correct Σn³ = 1296 for n = 8", "(Rs. 43,560)" at the end
_NAMED_VALUE = re.compile(r"\bcorrect\b[^=]*=\s*(-?\d[\d,]*(?:\.\d+)?)(?!\s*[+\-×*/^])", re.I)
_VALUE_IN_BRACKETS = re.compile(r"\(\s*(?:Rs\.?\s*)?(-?\d[\d,]*(?:\.\d+)?)\s*[^()]{0,6}\)\s*\.?\s*$")
# "Definition of rusting (1 mark) + balanced chemical equation (1 mark)": two points in one line
_SUBPOINT = re.compile(r"(?P<text>[^+]+?)\s*\(\s*(?P<m>\d+(?:\.\d+)?|½)\s*marks?\s*\)", re.I)
_EXACT_WORDS = re.compile(r"\b(?:choice|word\s+identification|correct\s+word|fill(?:ed)?\s+in|blank|option)\b", re.I)


def _marks(v: str) -> float:
    return {"½": 0.5, "¼": 0.25, "¾": 0.75}.get(v) or float(v)


@dataclass
class Point:
    id: str
    marks: float
    text: str
    kind: str = "meaning"
    part: str | None = None
    expected: list[str] = field(default_factory=list)


@dataclass
class Rubric:
    kind: str
    points: list[Point] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    deductions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    stated_total: float | None = None

    @property
    def total(self) -> float:
        return sum(p.marks for p in self.points)

    def to_dict(self) -> dict:
        return {**asdict(self), "total": self.total}


def question_kind(question_text: str | None) -> str:
    """OPEN for a writing task ("Draft a notice ...", "Write a diary entry ..."), POINTS otherwise."""
    text = question_text or ""
    return OPEN if _WRITING.search(text) and _WRITING_VERB.search(text) else POINTS


def _clean(line: str) -> str:
    return _BULLET.sub("", line.strip()).strip()


def _key_parts(key_text: str) -> dict[str, str]:
    """The key's answer to each part: {"a": "since", "b": "otherwise"}."""
    parts: dict[str, str] = {}
    cur = None
    for raw in (key_text or "").splitlines():
        line = _clean(raw)
        if m := _TABLE_ROW.match(raw.strip()):
            cells = [c.strip() for c in m.group(2).split("|") if c.strip()]
            parts[m.group(1)] = cells[-1] if cells else ""  # the row's last column: the correction / answer
            cur = None
        elif m := _PART_LINE.match(line):
            cur = m.group(1)
            parts[cur] = m.group(2).strip()
        elif cur and line and not _SCHEME_HEAD.match(line):
            parts[cur] = f"{parts[cur]} {line}".strip()
        elif _SCHEME_HEAD.match(line):
            cur = None
    return {k: re.sub(r"\s*\(\s*\d+(?:\.\d+)?\s*marks?\s*\)\s*$", "", v, flags=re.I).strip() for k, v in parts.items()}


def _numbers(text: str) -> list[str]:
    return [n.replace(",", "").replace("Rs.", "").replace("Rs", "").strip() for n in _NUMBER.findall(text)]


def _final_answers(key_text: str) -> list[str]:
    """Values the key states as the answer: "Answer: 1030301", "= 20 days", "x = 20"."""
    found = []
    for line in (key_text or "").splitlines():
        if m := re.search(r"\banswer\s*[:=]\s*(.+)$", line, re.I):
            found += _numbers(m.group(1))[:1]
    return found


def _kind_and_expected(text: str, part_answer: str | None, key_text: str) -> tuple[str, list[str]]:
    if _UNIT_WORDS.search(text):
        units = re.findall(r"\(([^)]{1,15})\)", text)
        if not units:
            m = re.search(r"S\.?I\.?\s*Unit\s*:\s*([^\n]+)", key_text or "", re.I)
            units = [u.strip() for u in re.split(r"\bor\b|/(?![a-zA-Z²³]{1,3}\b)", m.group(1)) if u.strip()] if m else []
        return "unit", [a.strip() for u in units for a in re.split(r"\s+or\s+|,\s*", u) if a.strip()]
    answer = part_answer or key_text or ""
    if (_EQUATION_WORDS.search(text) or _REACTION_WORDS.search(text)) and _ARROW.search(answer):
        eq = [part_answer] if part_answer and _ARROW.search(part_answer) else []
        return "equation", eq
    if _EXACT_WORDS.search(text):
        word = re.findall(r"\(([A-Za-z][A-Za-z'\- ]{0,25})\)", text)
        word = [w for w in word if not _PART_REF.fullmatch(f"({w})")]
        if not word and part_answer and len(part_answer.split()) <= 3:
            word = [part_answer.strip(" .")]
        if word:
            return "exact", word
    nums = _numbers(text)
    if nums and _NUMBER_WORDS.search(text):
        return "number", nums[-1:]
    # "... for n = 10: 440." -> 440 (the value after the colon), else "Correct n = 9", else "(Rs. 43,560)"
    if m := (re.search(r":\s*(-?\d[\d,]*(?:\.\d+)?)\s*\.?\s*$", text) or _NAMED_VALUE.search(text)
             or _VALUE_IN_BRACKETS.search(text)):
        return "number", [m.group(1).replace(",", "")]
    return "meaning", []


def _scheme_lines(key_text: str, key_criteria: list[str]) -> list[str]:
    """The marking-scheme lines: the key's criteria, else the lines after its "Marking Scheme" heading."""
    lines = [_clean(l) for l in key_criteria or [] if l and l.strip()]
    if any(_CBSE_POINT.match(l) or _SET_POINT.match(l) or _PER_ITEM.match(l) for l in lines):
        return lines
    out, inside = [], False
    for raw in (key_text or "").splitlines():
        line = _clean(raw)
        if _SCHEME_HEAD.match(line):
            inside = True
            out.append(line)
        elif inside and line:
            out.append(line)
    return out or lines


def build_rubric(question_text: str | None, key_text: str | None, key_criteria: list[str] | None,
                 max_marks: float | None) -> Rubric:
    kind = question_kind(question_text)
    rubric = Rubric(kind)
    parts = _key_parts(key_text or "")
    question_parts = sorted({m.group(1) for m in re.finditer(r"(?m)^\s*\(\s*([a-h])\s*\)", question_text or "")})
    pending: Point | None = None  # a point whose text wraps onto the next line
    line_points: list[list[Point]] = []  # the points each marking line gave (a split line gives several)
    for line in _scheme_lines(key_text or "", key_criteria or []):
        if _SECTION.match(line) and not _SCHEME_HEAD.match(line):
            break  # the next section's heading: the scheme ended
        before = len(rubric.points)
        pending = _read_line(line, rubric, parts, question_parts, kind, key_text or "", pending)
        if len(rubric.points) > before:
            line_points.append(rubric.points[before:])
    _parts_in_order(line_points, question_parts, parts)
    first = next((l for l in (key_text or "").splitlines() if l.strip()), "")
    if rubric.stated_total is None and (m := _HEADING_MARKS.search(first)):
        rubric.stated_total = float(m.group(1))
    return _validated(rubric, question_text or "", max_marks, key_text or "")


def _read_line(line: str, rubric: Rubric, parts: dict[str, str], question_parts: list[str], kind: str,
               key_text: str, pending: Point | None) -> Point | None:
    """One marking-scheme line into the rubric; returns the point whose text may run on into the next line."""
    if m := _SCHEME_HEAD.match(line):
        if m.group("total"):
            rubric.stated_total = float(m.group("total"))
        return None
    if _TABLE_HEAD.match(line):
        return pending
    if _DEDUCT.match(line):
        rubric.deductions.append(line.strip("() ."))
        return None
    if m := _PER_ITEM.match(line):
        items = sorted(parts) or question_parts
        if not items:
            rubric.problems.append(f"'{line}' gives marks per item, but the key lists no items (a), (b), ...")
            return None
        for it in items:
            k, expected = _kind_and_expected(m.group("text"), parts.get(it), key_text)
            if k == "meaning" and parts.get(it) and len(parts[it].split()) <= 6:
                k, expected = "exact", [parts[it]]
            rubric.points.append(Point(str(len(rubric.points) + 1), _marks(m.group("m")),
                                       f"({it}) {m.group('text')}", k, it, expected))
        return None
    m = _CBSE_POINT.match(line) or _SET_POINT.match(line)
    if not m:
        if pending is not None and not line.endswith(":"):
            pending.text = f"{pending.text} {line}".strip()  # the point's text runs on
            return pending
        if line:
            rubric.notes.append(line)
        return pending
    text = m.group("text").strip()
    refs = _PART_REF.findall(text)
    part = refs[0] if len(set(refs)) == 1 and refs[0] in "abcdefgh" else None
    k, expected = _kind_and_expected(text, parts.get(part) if part else None, key_text)
    if part is None and k == "exact":  # "Correct preposition choice (since)": the part whose answer it is
        part = next((pp for pp, ans in parts.items() if ans.strip(" .").lower() in {e.lower() for e in expected}), None)
    if kind == OPEN:
        k, expected = "criterion", []
    subs = list(_SUBPOINT.finditer(text))
    if kind != OPEN and len(subs) >= 2 and abs(sum(_marks(x.group("m")) for x in subs) - _marks(m.group("m"))) < 1e-9:
        for x in subs:  # split it: each sub-point is checked on its own
            sub_text = x.group("text").strip(" .;")
            sk, sexp = _kind_and_expected(sub_text, parts.get(part) if part else None, key_text)
            rubric.points.append(Point(str(len(rubric.points) + 1), _marks(x.group("m")), sub_text, sk, part, sexp))
        return None
    point = Point(str(len(rubric.points) + 1), _marks(m.group("m")), text, k, part, expected)
    rubric.points.append(point)
    return point


def _parts_in_order(line_points: list[list[Point]], question_parts: list[str], parts: dict[str, str]) -> None:
    """Marking lines that name no part but match the paper's parts one for one ((a), (b), (c) and three lines) belong
    to those parts in order; an equation point then expects its part's equation."""
    if not question_parts or len(line_points) != len(question_parts) or any(p.part for ps in line_points for p in ps):
        return
    for part, points in zip(question_parts, line_points):
        for p in points:
            p.part = part
            if p.kind == "equation" and not p.expected and parts.get(part):
                p.expected = [re.sub(r"^[A-Za-z ]{3,25}:\s*", "", e.strip()) for e in re.split(r"(?<=[.)])\s+(?=[A-Z0-9])", parts[part])
                              if _ARROW.search(e)][:1]  # without its label ("Chemical Equation: ...")


def _validated(rubric: Rubric, question_text: str, max_marks: float | None, key_text: str = "") -> Rubric:
    """Problems for the teacher's review: marks that do not add up, per question and per part."""
    if not rubric.points:
        # No marking scheme: the key's answer is one point worth the whole question (a short answer is exact)
        if max_marks:
            answer = re.sub(r"\s+", " ", re.sub(r"(?i)^\s*(?:answer|ans|solution)\s*[:.\-]\s*", "", key_text or "")).strip(" .")
            exact = bool(answer) and len(answer.split()) <= 4
            rubric.points.append(Point("1", max_marks, "Matches the key's answer", "exact" if exact else "meaning",
                                       None, [answer] if exact else []))
            rubric.notes.append("No marking scheme in the key: the answer is graded as a whole")
        else:
            rubric.problems.append("No marking scheme in the key and no marks for the question")
        return rubric
    total = rubric.total
    if max_marks is not None and abs(total - max_marks) > 1e-9:
        rubric.problems.append(f"Marking points add up to {total:g}, the question has {max_marks:g} marks")
    if rubric.stated_total is not None and abs(total - rubric.stated_total) > 1e-9:
        rubric.problems.append(f"Marking points add up to {total:g}, the key says {rubric.stated_total:g} in total")
    for part, part_marks in _question_part_marks(question_text).items():
        got = sum(p.marks for p in rubric.points if p.part == part)
        if got and abs(got - part_marks) > 1e-9:
            rubric.problems.append(f"Part ({part}) has {part_marks:g} marks in the paper but {got:g} in the key")
    return rubric


def _question_part_marks(question_text: str) -> dict[str, float]:
    """Part marks the paper prints: "(a) Calculate ... (1.5 marks)" -> {"a": 1.5}."""
    out: dict[str, float] = {}
    for m in re.finditer(r"(?ms)^\s*\(\s*([a-h])\s*\)(.*?)(?=^\s*\(\s*[a-h]\s*\)|\Z)", question_text):
        if mm := re.search(r"\(\s*(\d+(?:\.\d+)?)\s*marks?\s*\)", m.group(2), re.I):
            out[m.group(1)] = float(mm.group(1))
    return out
