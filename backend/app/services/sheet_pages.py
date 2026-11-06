"""Pages in an answer sheet that belong to another student's paper.

A scan sometimes carries pages of a different answer book (another subject or class, e.g. a Class 12 Maths sheet
inside a Class 10 Science one). Each page's header (read with the page, see prompts.student_answer_prompt) is
compared with the exam:
- another subject, or a class two or more years away: the page is left out before answers are built (never
  graded). A class one year off ("XI" in a Class 12 exam) is a slip in the class box: the page stays;
- the same subject and class but another roll number than the rest of the sheet: kept, and listed for the teacher
  (it may be a misread roll number, or another student's page).
Pages without a header, or with a header that cannot be read, are kept.
"""
from __future__ import annotations

import re
from collections import Counter

_ALIASES = {
    "maths": ("math", "maths", "mathematics", "mathematic", "mat"),
    "science": ("science", "sci", "generalscience"),
    "socialscience": ("socialscience", "social", "sst", "socialstudies", "sscience"),
    "english": ("english", "eng", "englishlanguageandliterature", "englishcore"),
    "tamil": ("tamil", "tam", "தமிழ்"),
    "hindi": ("hindi", "hin", "हिंदी", "हिन्दी"),
    "physics": ("physics", "phy"),
    "chemistry": ("chemistry", "chem", "che"),
    "biology": ("biology", "bio"),
    "accountancy": ("accountancy", "accounts", "account", "acc", "accounting"),
    "economics": ("economics", "eco"),
    "businessstudies": ("businessstudies", "business", "bst"),
    "computerscience": ("computerscience", "computer", "cs", "comp"),
}
_ROMAN = {"ix": 9, "x": 10, "xi": 11, "xii": 12, "viii": 8, "vii": 7, "vi": 6}


def _subject_key(name: str | None) -> str | None:
    squashed = re.sub(r"[^\w]+", "", (name or "").casefold())
    if not squashed:
        return None
    for key, names in _ALIASES.items():
        if squashed in names or squashed.startswith(key):
            return key
    for key, names in _ALIASES.items():  # "maths basic", "science (086)"
        if any(squashed.startswith(n) for n in names if len(n) >= 4):
            return key
    return None


def class_number(name: str | None) -> int | None:
    """"10-C", "Class 12", "XII-A", "X C" -> 10, 12, 12, 10; None when there is no class number."""
    text = re.sub(r"^\W*(?:class|std|standard|grade)\W*", "", (name or "").strip().casefold())
    m = re.match(r"^(\d{1,2})(?!\d)", text)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    roman = re.match(r"^([ivx]+)(?![a-z])", text)
    return _ROMAN.get(roman.group(1)) if roman else None


def other_class(written: int | None, exam: int | None) -> bool:
    """A class two or more years away (Class 10 inside a Class 12 exam) is another paper. One year off ("XI" in a
    Class 12 exam) is a common slip in the class box and says nothing: that page stays the student's."""
    return bool(written and exam and abs(written - exam) >= 2)


def roll_key(roll: str | None) -> str:
    # O/0 and I/l/1 are the usual misreads of a handwritten roll number: they count as the same
    return re.sub(r"[^0-9a-z]", "", (roll or "").casefold()).translate(str.maketrans("oil", "011"))


def check_pages(results, exam) -> tuple[set[int], list[dict], list[dict]]:
    """(page numbers to leave out, notes on those pages, pages with another roll number)."""
    want_subject = _subject_key(getattr(getattr(exam, "subject", None), "name", None))
    want_class = class_number(getattr(getattr(exam, "school_class", None), "name", None))
    headers = {}
    for page, result in results:
        header = getattr(result, "page_header", None) or {}
        if header:
            headers[page["page_number"]] = header
    excluded, notes = set(), []
    for number, header in sorted(headers.items()):
        subject, klass = _subject_key(header.get("subject")), class_number(header.get("class_name"))
        why = []
        if want_subject and subject and subject != want_subject:
            why.append(f"subject {header.get('subject')}")
        if other_class(klass, want_class):
            why.append(f"class {header.get('class_name')}")
        if why:
            excluded.add(number)
            notes.append({"page": number, "roll_number": header.get("roll_number"),
                          "reason": f"Left out: this page is from another paper ({', '.join(why)})."})
    rolls = Counter(roll_key(h.get("roll_number")) for n, h in headers.items()
                    if n not in excluded and roll_key(h.get("roll_number")))
    other_rolls = []
    if len(rolls) > 1:
        main = rolls.most_common(1)[0][0]
        for number, header in sorted(headers.items()):
            key = roll_key(header.get("roll_number"))
            if number not in excluded and key and key != main:
                other_rolls.append({"page": number, "roll_number": header.get("roll_number")})
    return excluded, notes, other_rolls
