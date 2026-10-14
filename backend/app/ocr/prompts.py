"""Strict, universally adaptable prompts for ADEM document perception.
The model performs visual understanding, OCR, layout extraction and transcription across any exam format.
"""

OCR_SYSTEM = (
    "You are the document reading engine of ADEM, an exam-marking system. "
    "You transcribe examination pages (printed or handwritten) into structured JSON.\n\n"
    "RULES:\n"
    "1. The image is the source of truth. Never invent text, question numbers or answers.\n"
    "2. Transcribe EVERYTHING on the page, top to bottom, left to right. Skipping text is the worst error: "
    "if a word cannot be read, write [unclear] in its place and keep going.\n"
    "3. Copy question labels exactly as printed/written (Q1, 1., 1), (1), I, 3(a), 3.a, (b)). If a block has no label, use null.\n"
    "4. Numbered points, bullets, options (A/B/C/D), match items and blanks INSIDE a question or answer are part of its text, "
    "not separate questions.\n"
    "5. Keep maths and science notation: x², H₂O, √, π, fractions as (a/b), arrows →, ↑. Keep tables as Markdown tables.\n"
    "6. Keep the original language (English, Tamil, Hindi, mixed) verbatim.\n"
    "7. Reply with one valid JSON object only."
)


def _text_layer_section(page_text: str | None, limit: int = 6000) -> str:
    """Embedded PDF text is exact (no OCR errors). Offered as a spelling/number reference, not as layout."""
    t = (page_text or "").strip()
    if len(t) < 20:
        return ""
    if len(t) > limit:
        t = t[:limit] + "\n[...]"
    return f"""
EMBEDDED TEXT OF THIS PAGE (exact characters extracted from the PDF; reading order may be jumbled):
<<<
{t}
>>>
Use it to get spelling, numbers, formulas and question labels exactly right. Use the image for structure and order.
"""


def question_paper_prompt(page_number: int, width: int, height: int, page_text: str | None = None, **_) -> str:
    return f"""This image is page {page_number} of a printed question paper ({width}x{height} pixels).
{_text_layer_section(page_text)}
Extract every question on the page, in reading order.

1. One item per question or sub-question that carries its own label (e.g. 3(a) and 3(b) are two items).
   MCQ options, match-the-following columns, fill-in blanks and tables stay inside question_text.
2. raw_question_number: the label exactly as printed, or null when the block has no label.
   - A page that starts with the rest of a question from the previous page (text, table, options): output it
     FIRST with raw_question_number null. Never drop it.
   - A page that starts with a sub-part like (b): raw_question_number "(b)".
3. question_text: the complete text, verbatim, without the label. Do not summarise or shorten.
4. marks: the marks printed for this question (e.g. "[2]", "(3 marks)"), or from a section rule such as
   "4 x 2 = 8" -> 2. Never use a section total as one question's marks. null if not shown.
5. section: the heading of the section this question is in (as printed), or null.
6. Section headings, general instructions and reading passages are not questions: put passages into the
   question_text of the first question that uses them; skip headers like school name, time, max marks.
7. bbox: the question's box in image pixels {{"x","y","width","height"}}, or null. confidence: 0.0-1.0.

Return JSON in exactly this shape:
{{"page_number": {page_number}, "questions": [{{"raw_question_number": null, "question_text": "", "question_type": "descriptive", "marks": null, "section": null, "confidence": 0.0, "bbox": null}}]}}
question_type is one of: mcq, short_answer, descriptive, fill_blank, true_false, match, numerical, other."""


def answer_key_prompt(page_number: int, width: int, height: int, page_text: str | None = None, **_) -> str:
    return f"""This image is page {page_number} of an official answer key / marking scheme ({width}x{height} pixels).
{_text_layer_section(page_text)}
Extract the answer for every question on the page, in reading order.

1. question_number: the label exactly as written (e.g. "1", "Q1", "3(a)", "(b)"), or null when the block has no label.
   Never infer a number from the order. A page that starts with the rest of the previous page's answer:
   output it FIRST with question_number null. Never drop it.
2. answer_text: the complete model answer, verbatim (lists, steps, formulas, tables as Markdown).
3. marks: total marks for this question only. If the scheme lists per-point marks ("1 Mark: ...", "½ mark each"),
   use their sum. Never use a section total. null if not shown.
4. criteria: each marking point as written (e.g. "1 Mark: states the purpose").
5. accepted_answers / keywords: only if explicitly listed, else [].
6. bbox in image pixels {{"x","y","width","height"}} or null. confidence 0.0-1.0.

Return JSON in exactly this shape:
{{"page_number": {page_number}, "answers": [{{"question_number": null, "answer_text": "", "marks": null, "criteria": [], "accepted_answers": [], "keywords": [], "confidence": 0.0, "bbox": null}}]}}"""


def student_answer_prompt(page_number: int, width: int, height: int,
                          canonical_questions: list[str] | None = None, **_) -> str:
    labels = ""
    if canonical_questions:
        labels = f"""
Question labels that exist in this exam: {", ".join(canonical_questions)}.
Use this list only to read an unclear handwritten label (e.g. a 1 with a hook that looks like 7).
If the student clearly wrote something else, copy what is written. Never assign a label the student did not write.
"""
    return f"""This image is page {page_number} of a student's handwritten answer sheet ({width}x{height} pixels).
{labels}
Transcribe every answer on the page, in reading order.

1. Start a new item ONLY where the student wrote a question label (Q3, 3., 3), 3(a), (b), Ans 4 ...),
   usually at the left margin or at the start of a line.
2. question_number: that label exactly as written. Use null for text with no label, for example the
   continuation of an answer from the previous page at the top of this page. Output that continuation FIRST.
3. Numbered points, (i)/(ii), bullets and steps inside an answer belong to that answer's text.
4. answer_text: the student's words exactly as written, every line, including spelling mistakes.
   Do not correct, complete or improve anything. Do not use your own knowledge.
   Unreadable word -> [unclear]. Crossed-out text -> leave it out. Drawing -> [diagram: short description].
   Maths: keep every step, =, signs, powers (x²), fractions (a/b), roots (√). Tables as Markdown tables.
5. ocr_confidence: how sure you are of the transcription (0.0-1.0).
   question_number_confidence: how sure you are of the label (0.0-1.0).
6. bbox: the answer's box in image pixels {{"x","y","width","height"}}, or null.

Return JSON in exactly this shape:
{{"page_number": {page_number}, "answers": [{{"question_number": null, "answer_text": "", "ocr_confidence": 0.0, "question_number_confidence": 0.0, "bbox": null}}]}}"""


EVAL_SYSTEM = (
    "You are a strict, fair examiner's assistant. Evaluate the student's answer ONLY against the official "
    "answer key and marking criteria provided. Do not reward information that is not in the student's answer. "
    "Do not use outside knowledge to award marks the key does not support. Do not penalise spelling or "
    "grammar unless the criteria say language accuracy matters. Never award more than the maximum marks. "
    "Text marked [UNCLEAR] could not be read; do not assume what it said. Reply with a single JSON object and nothing else."
)


def evaluation_prompt(question_number: str, question_text: str, answer_key_text: str,
                      criteria: list[str], accepted: list[str], keywords: list[str],
                      max_marks: float, student_answer: str) -> str:
    def lst(xs):
        return "\n".join(f"- {x}" for x in xs) if xs else "(none provided)"
    return f"""QUESTION {question_number} (maximum marks: {max_marks:g})
{question_text}

OFFICIAL ANSWER KEY
{answer_key_text}

MARKING CRITERIA
{lst(criteria)}

ACCEPTED ALTERNATIVE ANSWERS
{lst(accepted)}

KEYWORDS
{lst(keywords)}

STUDENT ANSWER (verbatim transcription)
{student_answer}

HOW TO MARK
- Compare the MEANING of the student's answer with the key. Different wording, order or synonyms that say the
  same thing earn the same credit; an accepted alternative answer earns full credit.
- If marking criteria are listed, go through them one by one and award each point the student covers.
- Numerical/maths: check the method steps and the final answer against the key; give step marks if the criteria allow.
- Nothing relevant, blank, or only [UNCLEAR]: 0 marks.
- Award between 0 and {max_marks:g}, in steps of 0.5.

Return JSON in exactly this shape:
{{"marks_awarded": 0, "max_marks": {max_marks:g}, "decision": "CORRECT | PARTIALLY_CORRECT | INCORRECT", "matched_points": ["..."], "missing_points": ["..."], "feedback": "one or two sentences for the teacher", "confidence": 0.0}}"""


GEN_ANSWER_KEY_SYSTEM = (
    "You are an academic examiner and curriculum specialist for ADEM. "
    "MODEL: blaifa/InternVL3_5:4B. "
    "Read the verified questions from the examination question paper and generate suggested answers for each question. "
    "Never invent questions or extra subquestions. For every question provided, generate a comprehensive model answer, "
    "marking criteria, essential keywords, and accepted alternative answers. Reply with a single JSON object and nothing else."
)


def generate_answer_key_prompt(exam_name: str, questions: list[dict]) -> str:
    lines = []
    for q in questions:
        lines.append(
            f"QUESTION {q['display_number']} (ID: {q['id']}, max marks: {q['max_marks']})\n"
            f"Type: {q.get('question_type') or 'descriptive'}\n"
            f"Question text: {q['question_text']}"
        )
    formatted = "\n\n".join(lines)
    return f"""Generating reference answer key and generate suggested answers for exam: {exam_name}
For each verified question from the question paper listed below, generate:
1. "answer_text": An authoritative, accurate model answer appropriate for the question type and marks.
2. "marks": Allocated marks equal to the question's maximum marks.
3. "criteria": List of distinct step or point marking criteria.
4. "keywords": Key technical/academic terms.
5. "accepted_answers": Acceptable alternative answers or phrasings.

VERIFIED QUESTIONS:
{formatted}

RULES:
- Do not invent new questions or answers.
- Preserve the exact question numbers and IDs.
- Return an answer for EVERY verified question listed above.

Return JSON in exactly this shape:
{{"answers": [{{"exam_question_id": "...", "question_number": "1", "answer_text": "...", "marks": 2.0, "criteria": ["..."], "keywords": ["..."], "accepted_answers": ["..."]}}]}}"""

