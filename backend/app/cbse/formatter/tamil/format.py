"""Tamil exam format: every Tamil rule the shared parsers use, kept out of the English format.

The English parsers (doc_structure, numbering, key_segmentation, ocr_recovery, evaluation_rules) call into this
module only for text that contains Tamil script (`has_tamil`), so English text never meets a Tamil rule. Under a
non-Tamil subject `has_tamil` is always False (paper_format), so those papers never meet a Tamil rule at all.
Where Tamil text needs a different answer than English (exam total, question type, page furniture), the function
here decides alone; elsewhere it adds the Tamil forms the English rule cannot see.

Reference layout: Tamil Nadu SSLC Tamil paper (8501, 2025):
  header  "கால அளவு : 3.00 மணி நேரம்"  "[ மொத்த மதிப்பெண்கள் : 100"  notes "அறிவுரைகள் :" / "குறிப்புகள் :"
  section "பகுதி - II" + "(மதிப்பெண்கள் : 18)", sub-sections "பிரிவு - 1"; rule "குறிப்பு : ... 4x2=8"
  MCQ     options (அ) (ஆ) (இ) (ஈ), "... தேர்க." / "தெரிவு செய்க"; either-or "(அ) ... அல்லது (ஆ) ..."
  footer  "[ திருப்புக" (turn over), "- o O o -" (end of paper)
"""
from __future__ import annotations
import re
from ....services import paper_format

_TAMIL_CHAR = re.compile(r"[஀-௿]")
_INDIC_CHAR = re.compile(r"[ऀ-෿]")


def has_tamil(text: str | None) -> bool:
    """Text in Tamil script that the Tamil rules apply to: never under a non-Tamil subject."""
    return bool(text) and paper_format.tamil_rules_apply() and bool(_TAMIL_CHAR.search(text))


# ---------------------------------------------------------------- question numbers

# Sub-part letters in order: (அ) (ஆ) (இ) ... are (a) (b) (c) ... Stops before ஐ, which would read as roman "i".
SUB_LETTERS = "அஆஇஈஉஊஎஏ"
_SUB_LATIN = str.maketrans(SUB_LETTERS, "abcdefgh")
# A sub-part letter standing alone ("(அ)", "அ)", "1அ"), not the first letter of a word ("அவர்")
_SUB_TOKEN = re.compile(rf"([{SUB_LETTERS}])(?![஀-௿])")
_LABEL_WORD = r"(?:வினா|கேள்வி|விடை|பதில்)"


def latin_subparts(s: str) -> str:
    """'1 (அ)' -> '1 (a)': sub-part letters to the Latin letters the numbering code understands."""
    return _SUB_TOKEN.sub(lambda m: m.group(1).translate(_SUB_LATIN), s)


def latin_label(s: str) -> str:
    """A Tamil label in the form the English numbering rules read: "வினா எண் 3 (அ)" -> "வினா 3 (a)"."""
    return re.sub(rf"^(\s*{_LABEL_WORD})\s*எண்", r"\1", latin_subparts(s))


# "34 -க்குக் கட்டாயமாக" (to [question] 34, compulsorily), "21 -வது வினா" (the 21st question): a number that a
# case ending follows is part of a sentence, never a question label
_NUMBER_IN_SENTENCE = re.compile(r"^\s*\d{1,3}\s*[-–]?\s*(?:வது|ஆவது|ஆம்|க்கு|இல்|இன்)")


def extract_label_prefix(s: str) -> tuple[str | None, str] | None:
    """A Tamil question label at the start of the text, (None, text) when the text starts with a number that is
    not a label, or None to leave the text to the English rules."""
    if _NUMBER_IN_SENTENCE.match(s):
        return None, s
    # "வினா 1", "வினா எண் 3 (அ)", "கேள்வி 2:", "விடை 4." (question / answer [number] N)
    m = re.match(rf"^\s*{_LABEL_WORD}\s*(?:எண்)?\s*[\.\:\-]?\s*([0-9]{{1,3}}(?:\s*\(\s*[{SUB_LETTERS}a-zA-Z]\s*\))?)[\.\:\)\s\-\,\>\→]*(.*)", s, re.DOTALL)
    if m:
        rest = m.group(2).strip()
        return latin_subparts(re.sub(r"\s+", "", m.group(1))), (rest if rest else s)
    # Sub-part labels: "3(அ) ...", "3 அ) ...", "(ஆ) ...", "இ) ..."
    m = re.match(rf"^\s*([0-9]{{1,3}})\s*\(?\s*([{SUB_LETTERS}])\s*\)[\.\:\s\-]*(.*)", s, re.DOTALL)
    if m:
        rest = m.group(3).strip()
        return f"{m.group(1)}({latin_subparts(m.group(2))})", (rest if rest else s)
    m = re.match(rf"^\s*(?:\(\s*([{SUB_LETTERS}])\s*\)|([{SUB_LETTERS}])\s*[\)\.])[\.\:\s\-]*(.*)", s, re.DOTALL)
    if m:
        rest = m.group(3).strip()
        return f"({latin_subparts(m.group(1) or m.group(2))})", (rest if rest else s)
    return None


# ---------------------------------------------------------------- question paper layout

# "marks" in English or Tamil (மதிப்பெண் / மதிப்பெண்கள் / மதி.)
_MARK_WORD = r"(?:marks?|m|மதிப்பெண்கள்|மதிப்பெண்|மதி\.?)"

_INSTRUCTION_PATTERNS = [
    # "answer all/any ... questions", notes "குறிப்பு(கள்) :", instructions "அறிவுரை(கள்) :", time "நேரம் :" / "கால அளவு :"
    re.compile(r"^\s*(?:(?:அனைத்து|ஏதேனும்|எவையேனும்|பின்வரும்).{0,60}விடையளி|குறிப்பு(?:கள்)?\s*:|அறிவுரை(?:கள்)?\s*:"
               r"|நேரம்\s*:|கால\s*அளவு\s*:)"),
    # "பாடலைப் படித்து ..." (read the poem ...), "உரைப்பத்தியைப் படித்து ..." (read the passage ...)
    re.compile(r"^\s*\S*(?:பாடல|பத்தி|செய்யுள)\S*\s+படித்து"),
    # A section's marks on their own: "(மதிப்பெண்கள் : 15)"
    re.compile(r"^\s*\(?\s*மதிப்பெண்கள்?\s*:\s*\d+(?:\.\d+)?\s*\)?\s*$"),
]

# Marks rule in a section or note: "4 x 2 = 8", "தலா 2 மதிப்பெண்" / "2 மதிப்பெண்கள் வீதம்" (2 marks each)
_MARKS_RULE_PATTERNS = [
    re.compile(rf"(\d+)\s*(?:questions?|qn|q|வினா\S*)?\s*[×x*]\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}?\s*=\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}?", re.IGNORECASE),
    re.compile(rf"(\d+(?:\.\d+)?)\s*{_MARK_WORD}\s+(?:each|வீதம்)", re.IGNORECASE),
    re.compile(r"each\s+(?:question\s+)?(?:carries|is\s+worth)\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?", re.IGNORECASE),
    re.compile(rf"\(\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}\s*each\s*\)", re.IGNORECASE),
    re.compile(rf"தலா\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}"),
]

# The paper total says "மொத்த" (total): a bare "(மதிப்பெண்கள் : 15)" is one section's marks, not the paper's
_MAX_MARKS_PATTERN = re.compile(
    r"(?:(?:maximum|max\.?|total)\s*(?:marks?)?|மொத்த\s*மதிப்பெண்கள்?)\s*[:=\-]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_INLINE_MARKS_PATTERN = re.compile(rf"\(\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}\s*\)\s*$", re.IGNORECASE)
# Header lines carry a value, so a question that merely mentions "நேரம்" (time) is not a header
_HEADER_META = re.compile(r"(?:நேரம்|கால\s*அளவு|மொத்த\s*மதிப்பெண்கள்?)\s*[:\-]\s*\d")
# Paper titles: "மொழிப்பாடம் - பகுதி I - தமிழ்" (language paper), "வினாத்தாள்" (question paper), "பொதுத் தேர்வு",
# a line ending in "தேர்வு" (exam): "பத்தாம் வகுப்பு தமிழ் தேர்வு"
_TITLE = re.compile(r"மொழிப்பாடம்|வினாத்தாள்|(?:பொதுத்?|அரையாண்டு|காலாண்டு|முழு\s*ஆண்டு|திருப்புதல்)\s*தேர்வு|தேர்வு\s*$", re.M)
_DURATION = re.compile(r"(?:கால\s*அளவு|நேரம்)\s*:?\s*(\d+(?:\.\d+)?)\s*மணி")

# Section heading: "பகுதி – அ", "பகுதி - II", "பிரிவு 2" (not "பகுதியில்", "பகுதி அனைத்து ...")
_SECTION = r"(?:பகுதி|பிரிவு)\s*[-–—:]?\s*(?:[அ-ஔ]|[ivxIVX]+|[0-9]+|[A-Za-z])(?![஀-௿\w])"
_SECTION_LINE = re.compile(rf"^\s*{_SECTION}")
_PART = re.compile(r"^\s*பகுதி")
_DIVISION = re.compile(r"^\s*பிரிவு")

# Commands and question words: "விளக்குக" (explain), "எழுதுக" (write), "அமைக்க" (form), "தேர்க" (choose),
# "காண்க" (find), "ஏன்" (why), "எவ்வாறு" (how), "யாவர்" (who are they)
_QUESTION_WORD = re.compile(
    r"[஀-௿]+(?:ுக|க்க|வும்|்க)(?=[\s.?!:,;)]|$)"
    r"|(?:^|\s)(?:ஏன்|எவ்வாறு|எப்படி|யாவை|யாவர்|யார்|என்ன|எது|எவை|எங்கு|எத்தனை)(?=[\s.?!:,;]|$)"
)
_MCQ_OPTION = re.compile(r"(?:^|\s)\(?\s*([அஆஇஈ]|[a-dA-D])\s*[\)\.]")
_CHOOSE = re.compile(r"சரியான\s*விடையைத்?\s*தேர்|தேர்ந்தெடு|தேர்க(?![஀-௿])|தெரிவு\s*செய்க|\bchoose\s+the\s+correct\b", re.I)

# "அல்லது" (or) alone on a line: the parts either side are alternatives, the student answers one
_EITHER_OR = re.compile(r"^\s*[-–—(\[]*\s*அல்லது\s*(?:/\s*(?:OR\s*)?)?[-–—)\]]*\s*$", re.M | re.I)
# "[ திருப்புக" (turn over) at a page foot, "- o O o -" at the end of the paper
_PAGE_FURNITURE = re.compile(r"^\s*\[?\s*திருப்புக\s*\]?\s*$|^\s*-?\s*o\s*O\s*o\s*-?\s*$", re.M)
# A line with a web address or e-mail and no Tamil: a site's watermark or footer the OCR joined to a question
_WEB_LINE = re.compile(r"^[^஀-௿\n]*(?:www\.|https?://|\S+@\S+\.\w+)[^஀-௿\n]*$", re.M | re.I)


def starts_instruction(line: str) -> bool:
    """A line that opens a note or instruction ("குறிப்பு : ...", "(மதிப்பெண்கள் : 18)", "பாடலைப் படித்து ...")."""
    return any(p.search(line) for p in _INSTRUCTION_PATTERNS)


_NUMBER_WORDS = {"ஒன்று": 1, "ஒரு": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7,
                 "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10}
# "எவையேனும் நான்கு வினாக்களுக்கு மட்டும் விடையளிக்கவும்" (answer any four questions only)
_ANSWER_ANY = re.compile(r"(?:எவையேனும்|ஏதேனும்)\s*(\d{1,2}|[஀-௿]+)\s*வினா")
# "21 -வது வினாவிற்குக் கட்டாயமாக" (question 21 compulsorily), "வினா எண் 34 -க்குக் கட்டாயமாக"
_COMPULSORY = re.compile(r"(\d{1,3})\s*-?\s*(?:வது|ஆவது)\s*வினா\S*\s*கட்டாய|வினா\s*எண்\s*(\d{1,3})\s*-?\s*க்குக்?\s*கட்டாய")


def answer_any_count(text: str) -> int | None:
    """N of "answer any N questions" in a section's note."""
    m = _ANSWER_ANY.search(text)
    if not m:
        return None
    word = m.group(1)
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word)


def compulsory_numbers(text: str) -> set[str]:
    """Question numbers a note makes compulsory."""
    return {a or b for a, b in _COMPULSORY.findall(text)}


def is_instruction(s: str) -> bool:
    if any(p.search(s) for p in _INSTRUCTION_PATTERNS):
        return True
    return any(p.search(s) for p in _MARKS_RULE_PATTERNS) and "?" not in s and len(s) < 120


def is_document_header(s: str) -> bool:
    if "?" in s:
        return False
    return bool(_HEADER_META.search(s)) or (len(s) < 80 and bool(_TITLE.search(s)) and not has_question_word(s))


def section_marks_rule(text: str) -> float | None:
    """Marks per question from a section rule: "15x1=15" -> 1, "தலா 2 மதிப்பெண்" -> 2."""
    for pat in _MARKS_RULE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(2) if len(m.groups()) >= 2 and m.group(2) else m.group(1))
            except (TypeError, ValueError):
                pass
    return None


def exam_total_marks(text: str) -> float | None:
    m = _MAX_MARKS_PATTERN.search(text)
    return float(m.group(1)) if m else None


def inline_marks(text: str) -> float | None:
    """A question's own marks at its end: "(5 மதிப்பெண்கள்)"."""
    m = _INLINE_MARKS_PATTERN.search(text)
    return float(m.group(1)) if m else None


# A line's own marks at its end: "(2)", "(½)", "(3 மதிப்பெண்கள்)". A bare number counts only at a line's end, so
# "(1) அனைத்து வினாக்களும் ..." (a numbered note) is never a mark.
_LINE_MARKS = re.compile(rf"[\(\[]\s*(\d+(?:\.\d+)?|½)\s*{_MARK_WORD}?\s*[\)\]]\s*$", re.IGNORECASE)
# The paper total repeated at its end: "மொத்தம்: 30 மதிப்பெண்கள்"
_TOTAL_LINE = re.compile(rf"^\s*மொத்தம்\s*[:\-]\s*\d+(?:\.\d+)?\s*{_MARK_WORD}?\s*$", re.IGNORECASE)


# A roman-numbered section: "I. சரியான விடையைத் தேர்ந்தெடுத்து எழுதுக. 10 × 1 = 10", "II. ... விடையளி"
_ROMAN_SECTION = re.compile(r"^\s*(?:I{1,3}|IV|VI{0,3}|IX|X)\s*[.)]\s+\S")
_SECTION_COMMAND = re.compile(r"விடையளி|விடை\s*தருக|எழுதுக|தேர்ந்தெடு|நிரப்புக|பொருத்துக")
# The rule line of a set of questions on its own: "5 × 2 = 10", "(4 வினாக்கள் × 3 மதிப்பெண்கள் = 12 மதிப்பெண்கள்)"
_RULE_LINE = re.compile(rf"^\s*\(?\s*\d+\s*(?:வினா\S*)?\s*[×xX*]\s*\d+(?:\.\d+)?\s*{_MARK_WORD}?\s*=\s*\d+(?:\.\d+)?\s*{_MARK_WORD}?\s*\)?\s*$")
# "பாடலைப் படித்து பின்வரும் வினாக்களுக்கு (12, 13, 14, 15) விடை தருக.": a poem / passage several questions share
_GROUP_INTRO = re.compile(r"^\s*\S*(?:பாடல|பத்தி|செய்யுள|கவிதை)\S*\s+படித்து")
_GROUP_NUMBERS = re.compile(r"\(\s*(\d{1,3}(?:\s*[,–\-]\s*\d{1,3})+)\s*\)")


def is_roman_section(text: str) -> bool:
    first = text.strip().partition("\n")[0]
    return bool(_ROMAN_SECTION.match(first)) and bool(section_marks_rule(text) is not None or _SECTION_COMMAND.search(first))


def is_rule_line(text: str) -> bool:
    return bool(_RULE_LINE.match(text.strip()))


def passage_group(text: str) -> set[int] | None:
    """The questions a shared passage or poem is for: {12, 13, 14, 15} from "(12, 13, 14, 15)" or "(12-15)", an empty
    set for "பின்வரும் வினாக்களுக்கு" (the questions that follow); None when the text opens no such passage."""
    if not _GROUP_INTRO.match(text):
        return None
    if m := _GROUP_NUMBERS.search(text):
        nums = [int(n) for n in re.findall(r"\d+", m.group(1))]
        return set(range(nums[0], nums[-1] + 1)) if re.search(r"[–\-]", m.group(1)) and len(nums) == 2 else set(nums)
    return set() if re.search(r"பின்வரும்\s*வினா", text) else None


def line_marks(line: str) -> float | None:
    m = _LINE_MARKS.search(line)
    return None if not m else 0.5 if m.group(1) == "½" else float(m.group(1))


def is_total_line(text: str) -> bool:
    return bool(_TOTAL_LINE.match(text))


def duration_minutes(text: str) -> int | None:
    """"கால அளவு : 3.00 மணி நேரம்" -> 180."""
    m = _DURATION.search(text)
    return round(float(m.group(1)) * 60) if m else None


def is_section_heading(s: str) -> bool:
    return bool(_SECTION_LINE.match(s))


def section_title(text: str, current: str | None) -> str:
    """The section a heading opens. "பிரிவு - 1" inside "பகுதி - II" is "பகுதி - II / பிரிவு - 1", so the பிரிவு 1
    of each பகுதி stays its own section; the marks line under a heading is not part of its title."""
    first = text.strip().splitlines()[0].strip() if text.strip() else text
    if not (_PART.match(first) or _DIVISION.match(first)):
        return text
    if _DIVISION.match(first) and current:
        part = current.split(" / ")[0]
        if _PART.match(part):
            return f"{part} / {first}"
    return first


def has_question_word(s: str) -> bool:
    return bool(_QUESTION_WORD.search(s))


def is_either_or_line(s: str) -> bool:
    return bool(_EITHER_OR.match(s))


def strip_page_furniture(text: str) -> str:
    return _WEB_LINE.sub("", _PAGE_FURNITURE.sub("", text)).strip()


def _is_mcq(t: str) -> bool:
    """Options (அ)-(ஈ), the OCR sometimes writing one as "(a)" or dropping a bracket. Three letters are enough
    unless a question mark follows them: "(அ) ... யார் ? (ஆ) ... எது ?" are sub-questions, not options."""
    found = list(_MCQ_OPTION.finditer(t))
    letters = {"அஆஇஈ".find(m.group(1)) if m.group(1) in "அஆஇஈ" else "abcd".find(m.group(1).lower()) for m in found}
    if not found or re.search(r"_{3,}|\.{5,}", t[found[0].start():]) or _LINE_MARKS.search(t[found[0].start():].split("\n")[0]):
        return False  # blanks or a mark after the first letter: parts to answer ("அ) ... (1)", "பிழையான சொல்: ____")
    return len(letters) >= 4 or (len(letters) == 3 and "?" not in t[found[0].start():])


# A letter ("கடிதம்"), essay ("கட்டுரை") or summary to write: a long answer, whatever lettered topics it lists
_LONG_WRITING = re.compile(r"(?:கடிதம்|கட்டுரை|பொழிப்புரை|சுருக்கம்)\s*(?:எழுது|வரை)")


def keyword_question_type(text: str) -> str | None:
    """The type a keyword or layout clue proves, or None. Options (அ)-(ஈ) decide before a blank does: a Tamil MCQ
    often is a sentence with a gap ("வெண்பா ______ ஓசை உடையது." + four options)."""
    t = text or ""
    if re.search(r"பொருத்துக|பொருத்தவும்|\bmatch\s+the\b", t, re.I):
        return "match"
    if re.search(r"சரியா\s*தவறா|சரி\s*(?:அல்லது|/)\s*தவறு|\btrue\s*(?:or|/)\s*false\b", t, re.I):
        return "true_false"
    if _LONG_WRITING.search(t):
        return "descriptive"
    if _is_mcq(t) or _CHOOSE.search(t):
        return "mcq"
    # "கோடிட்ட இடத்தை நிரப்புக" (fill the blank); a bare "நிரப்புக" can be "fill in the form"
    if re.search(r"கோடிட்ட\s*இட|இடத்தை\s*நிரப்பு|_{3,}|\.{5,}|\bfill\s+in\b", t, re.I):
        return "fill_blank"
    if re.search(r"கணக்கிடுக|கணக்கிடவும்|மதிப்பைக்?\s*காண்க|\bcalculate\b|\bfind\s+the\s+value\b", t, re.I):
        return "numerical"
    if re.search(r"ஓரிரு\s*சொற்களில்|ஒரு\s*சொல்லில்|சுருக்கமாக|\bin\s+one\s+word\b|\bbriefly\b", t, re.I):
        return "short_answer"
    return None


# ---------------------------------------------------------------- answer keys

# "marks" and "marking scheme" (மதிப்பெண்(கள்); மதிப்பீட்டுக் குறிப்பு / மதிப்பெண் பகிர்வு)
_MK = r"(?:marks?|m|மதிப்பெண்கள்|மதிப்பெண்)"
_MK_WORD = r"(?:marks?|மதிப்பெண்கள்|மதிப்பெண்)"
_SCHEME = r"(?:Marking\s+Scheme|மதிப்பீட்டுக்?\s*குறிப்பு(?:கள்)?|மதிப்பெண்\s*பகிர்வு|மதிப்பீட்டு\s*முறை|மதிப்பீட்டுத்?\s*திட்டம்)"
# One marking point: "1 Mark: ...", "(... marks ...)", "1 மதிப்பெண்: ...", "ஒவ்வொன்றுக்கும் 1 மதிப்பெண்"
CRITERION = re.compile(
    rf"(?:^|\n)\s*[o•\-\*]?\s*(\d+(?:\.\d+)?\s*{_MK_WORD}[:\s][^\n]+|1 mark per[^\n]+|\([^\)]+{_MK_WORD}[^\)]*\)[^\n]*|ஒவ்வொ[^\n]*மதிப்பெண்[^\n]*)",
    re.I,
)
# A line opening the marking scheme
SCHEME_LINE = re.compile(rf"^[^\n]*(?:\bMarking\s+Scheme\b|{_SCHEME})[^\n]*$", re.I | re.M)
# Keys list points without a scheme heading: "• கருத்து – 1 மதிப்பெண்", "1 மதிப்பெண்: கருத்து"
_POINT = re.compile(r"^\s*[•\-\*]?\s*(?:\d+(?:\.\d+)?\s*மதிப்பெண்\S*\s*[:\-–]\s*\S.*|\S.*[-–:(]\s*\d+(?:\.\d+)?\s*மதிப்பெண்\S*\s*\)?\s*)$", re.M)


def parse_criteria_marks(criteria: list[str], text: str = "") -> float | None:
    """A key's marks from its marking scheme: a stated total, else the sum of its points' marks."""
    m_tot = re.search(rf"{_SCHEME}\s*\(\s*(\d+(?:\.\d+)?)\s*{_MK}\s*(?:Total|மொத்தம்)?\s*\)", text, re.I)
    if m_tot:
        return float(m_tot.group(1))
    for c in criteria:
        m_tot = re.search(rf"\(\s*(\d+(?:\.\d+)?)\s*{_MK}\s*(?:Total|மொத்தம்)\s*\)", c, re.I)
        if m_tot:
            return float(m_tot.group(1))
    total, found = 0.0, 0
    for c in criteria:
        if re.search(r"\bdeduct\b|குறைக்க|குறைவு", c, re.I):  # "(... மதிப்பெண் குறைக்கவும்)" is a deduction note
            continue
        m_start = re.match(rf"^\s*[•\-\*]?\s*(\d+(?:\.\d+)?)\s*{_MK}(?![a-z])\s*[:\-–]", c, re.I)
        if m_start:
            total += float(m_start.group(1))
            found += 1
            continue
        m_end = re.search(rf"\(\s*(\d+(?:\.\d+)?)\s*{_MK}\s*\)\s*$|[-–:]\s*(\d+(?:\.\d+)?)\s*மதிப்பெண்\S*\s*$", c, re.I)
        if m_end:
            total += float(m_end.group(1) or m_end.group(2))
            found += 1
    return total if found > 0 and total > 0 else None


def extract_criteria_from_block(text: str) -> tuple[str, list[str]]:
    """Answer text and marking points; a point list with marks and no scheme heading is both."""
    ms_match = re.search(rf"(?:{_SCHEME}\s*(?:\([^\)]+\))?[:\s]*)(.*)", text, re.DOTALL | re.I)
    if not ms_match:
        return text.strip(), [m.group(0).strip() for m in _POINT.finditer(text)]
    # Under the heading every line is a point, its mark first or last ("1 மதிப்பெண் – ...", "... – 2 மதிப்பெண்கள்.");
    # a closing note ("குறிப்பு: any chosen topic is marked the same way") is not one: it stays with the answer
    # A note runs on over the lines after it ("... ஏற்ற சரியான,\nபொருத்தமான கட்டுரைக்கும் ...") until a line with marks.
    points, notes, in_note = [], [], False
    for line in (re.sub(r"^[o•\-\*]\s*", "", l.strip()) for l in ms_match.group(1).splitlines()):
        if not line:
            continue
        if line.startswith("குறிப்பு"):
            notes.append(line)
            in_note = True
        elif in_note and not _POINT.match(line):
            notes[-1] = f"{notes[-1]} {line}"
        else:
            points.append(line)
            in_note = False
    answer = "\n".join([text[:ms_match.start()].rstrip(" \t\n•*-").strip(), *notes]).strip()
    return answer, points


# ---------------------------------------------------------------- answer matching and grading

# Case/plural endings, longest first ("திருக்குறளை" and "திருக்குறள்" share the stem "திருக்குறள")
_SUFFIXES = ("களுக்கு", "களின்", "களில்", "களை", "கள்", "ுக்கு", "க்கு", "ிடம்", "ுடன்", "ோடு",
             "ின்", "ில்", "ால்", "ும்", "ுக", "வும்")
_INDIC_WORD = re.compile(r"[ऀ-෿]+")
_GLIDE_VOWELS = "ிீெேைுூொோா"  # vowel signs a "ய" / "வ" glide follows


def _stem(w: str) -> str:
    if w.endswith(("க்", "ச்", "த்", "ப்")) and len(w) > 4:  # sandhi doubling: "குறள்களைக் கொண்டது"
        w = w[:-2]
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    w = w.rstrip("ாிீுூெேைொோௌ்")  # trailing vowel sign / pulli
    # the glide before a case ending: "தாய்மொழியின்" -> "தாய்மொழிய" and "இயற்கையை" -> "இயற்கைய" meet "தாய்மொழி", "இயற்கை"
    if len(w) > 4 and w[-1] in "யவ" and w[-2] in _GLIDE_VOWELS:
        w = w[:-1].rstrip("ாிீுூெேைொோௌ்")
    return w


# Function words and question boilerplate, compared after stemming
_STOP_WORDS = {_stem(w) for w in (
    "மற்றும்", "ஒரு", "இது", "அது", "இந்த", "அந்த", "என்று", "என்ன", "எது", "ஆகும்", "உள்ள", "பற்றி",
    "யாவை", "யார்", "ஏன்", "எவ்வாறு", "வினா", "விடை", "மதிப்பெண்", "எழுதுக", "எழுதவும்", "விளக்குக",
    "கூறுக", "குறிப்பிடுக", "தருக", "காண்க", "பின்வரும்",
)}


def indic_tokens(text: str) -> set[str]:
    """Stemmed content words in Tamil or another Indian script, for matching an answer to its question."""
    if not _INDIC_CHAR.search(text or ""):
        return set()
    stems = (_stem(w) for w in _INDIC_WORD.findall(text))
    return {w for w in stems if len(w) >= 2 and w not in _STOP_WORDS}


# A deduction explained in Tamil feedback: "-வில்லை" (did not ...), "இல்லை" (not there), "விடுபட்ட" (left out),
# "தவறு" (wrong), "முழுமையற்ற" (incomplete), "குறைபாடு"/"குறைவு" (lacking)
_OMISSION_IN_FEEDBACK = re.compile(r"வில்லை|இல்லை|விடுபட|தவற|முழுமையற்ற|முழுமையில்ல|குறைபாடு|குறைவு")


def feedback_names_gap(feedback: str) -> bool:
    return has_tamil(feedback) and bool(_OMISSION_IN_FEEDBACK.search(feedback))

