"""Strict, universally adaptable prompts for ADEM document perception.
The model performs visual understanding, OCR, layout extraction and transcription across any exam format.
"""

OCR_SYSTEM = (
    "You are the document understanding, OCR, structure extraction, and question-mapping engine for ADEM. "
    "MODEL: Blaifa/InternVL3_5:4B. "
    "Your job is to accurately understand the supplied examination document image/PDF page and return structured information.\n\n"
    "CRITICAL PRINCIPLES:\n"
    "1. Read the actual document visually. Never invent text, question numbers, subquestions, or answers. Never autocomplete or finish incomplete answers.\n"
    "2. Detect element types from surrounding visual context (QUESTION, SUBQUESTION, SECTION, HEADING, INSTRUCTION, "
    "PASSAGE, TABLE, FORMULA, EQUATION, LIST, OPTION, ANSWER, CONTINUATION). "
    "Do NOT classify headings, instructions, passages, tables, or continuation lines as questions unless explicitly printed as a question.\n"
    "3. Question numbering: recognize any format (Q1, Q.1, Question 1, 1., 1), (1), I, II, 1(a), 1.a, 1-a, (b), (c)). "
    "Use surrounding typography, layout, and sequence to verify. If uncertain of a label, use null; never guess.\n"
    "4. Subquestions: detect a/b/c/i/ii only when genuine question parts. When a page starts with a subquestion like (b) or (c), keep raw_question_number as '(b)' or '(c)'. Never split answer choices (A/B/C/D), match items, or fill-in blanks into separate questions.\n"
    "5. Answer continuation: subsequent lines or numbered list items (e.g. 1), 2), bullet points) belong to the current question/answer. NEVER split continuation lines into separate questions.\n"
    "6. Mathematics & Science:\n"
    "   - Preserve vertical fractions and powers as inline expressions: [((2/3)⁻² × (3/4)⁻³) ÷ (8/9)⁻²].\n"
    "   - Preserve superscripts and formulas: (a + b)² = a² + b² + 2ab, x² + 1/x² = 34, 16x⁴ - 81y⁴, V = π(R² - r²)h.\n"
    "   - Preserve chemical equations, reaction arrows, and gas arrows: Na + H₂O → ________ + H₂ ↑, SO₂ + H₂O → ________, Zn + H₂SO₄ → ________ + H₂ ↑.\n"
    "7. Tables: preserve table structure as Markdown tables (| Header 1 | Header 2 |) with rows and cells. Never flatten table rows into unformatted text.\n"
    "8. Notice Boxes & Formats: preserve notice borders and formatted text layout.\n"
    "9. Passages: comprehension passages, poems, and source texts belong to the question context, not as separate question entities.\n"
    "10. Languages: preserve original language (English, Tamil, Hindi, or bilingual/mixed text) verbatim.\n"
    "11. Autocompletion Strictly Prohibited: When reading handwritten student answer sheets, NEVER autocomplete incomplete sentences or insert unwritten scientific explanations, reasons, or formulas (e.g. if the student writes 'no reaction occurs', transcribe ONLY that; do NOT append 'because copper is less reactive than zinc'). Transcribe ONLY visible ink strokes and stop exactly where the student stopped writing.\n"
    "12. Reply with a single valid JSON object and nothing else."
)


def question_paper_prompt(page_number: int, width: int, height: int) -> str:
    return f"""This image is page {page_number} of a printed question paper ({width}x{height} pixels).
Read the entire page visually. Adapt to any layout, curriculum, or typography. Identify every question label and transcribe each question completely.

UNIVERSAL EXTRACTION RULES:
1. DETECT ALL ELEMENTS: Extract EVERY question, problem, task, table, and exercise on the page.
   - Scan the ENTIRE page from top to bottom. If a previous section or exercise ends and a new section (e.g. "SECTION B: CREATIVE WRITING SKILLS") or new question starts in the middle or bottom half of the page, YOU MUST EXTRACT IT!
   - Look at the VERY TOP of the page. If there is a table, grid, or exercise continuation (e.g. an editing exercise with columns "Line | Incorrect Word | Correct Word" or fill-in blanks), YOU MUST EXTRACT IT as an item with raw_question_number null (or "cont"). NEVER SKIP OR OMIT A TABLE AT THE TOP OF THE PAGE!
2. PRESERVE STRUCTURE & TEXT: Transcribe full text verbatim without truncation or summarisation.
   - Mathematical expressions: inline vertical fractions and powers e.g. [((2/3)⁻² × (3/4)⁻³) ÷ (8/9)⁻²], superscripts e.g. x² + 1/x² = 6, 16x⁴ - 81y⁴, π, √.
   - Chemical equations: keep reaction arrows →, gas evolution ↑, and blanks ________ (e.g. Na + H₂O → ________ + H₂ ↑).
   - Tables: transcribe every row and cell as clean Markdown tables (| Line | Incorrect Word | Correct Word |).
3. QUESTION NUMBERING: Keep question labels exactly as printed (e.g. "1", "Q1", "Q7", "Q8", "3(a)", "(b)", "(c)").
   - DO NOT STRIP printed question labels like "Q7" or "Q8" from the question! If printed as "Q7. Reading Comprehension", set raw_question_number to "Q7" and question_text to "Reading Comprehension:...".
   - If page starts with a subquestion like (b) or (c), keep raw_question_number as "(b)" or "(c)". If unlabelled, set raw_question_number to null.
4. SUBQUESTIONS VS CHOICES: Only separate items if they are independent questions. Do NOT split multiple-choice options (A, B, C, D), match items, or fill-in blanks into separate entries; keep them within question_text.
5. MARKS & SECTIONS:
   - Identify the enclosing SECTION heading (e.g. "SECTION A: SHORT ANSWER QUESTIONS", "SECTION B: MEDIUM ANSWER QUESTIONS", "SECTION C: LONG ANSWER & WRITING SKILLS") and populate "section" with the full section title for every question in that section.
   - Extract marks printed next to the question or derived from section instructions (e.g. '4 questions x 2 marks = 8 Marks' -> 2 marks each, '4 questions x 3 marks = 12 Marks' -> 3 marks each, '2 questions x 5 marks = 10 Marks' -> 5 marks each).
   - CRITICAL: NEVER embed or include section headings (e.g. "SECTION C: LONG ANSWER & DETAILED QUESTIONS") or section instruction lines (e.g. "(2 questions x 5 marks = 10 Marks)") inside "question_text"! Store section titles ONLY in the "section" property.
   - NEVER repeat or duplicate question text, sentences, or topic headings within the same question entry.
6. CONTINUATIONS ACROSS PAGES:
   - When a question starts on one page and continues onto the next page (e.g. Question 4 or Question 6 table starts at the bottom of Page 1 and finishes at the top of Page 2), YOU MUST transcribe the continued text/table at the top of Page 2 completely.
   - Set raw_question_number to null or "cont".
7. BBOX & CONFIDENCE: Provide bbox in image PIXELS (x, y, width, height) or null. Confidence is 0.0 to 1.0.
8. JSON ESCAPING: When question text contains double quotes (e.g. "5R Principle"), YOU MUST escape them with backslashes (\\\"5R Principle\\\")! NEVER leave raw unescaped quotes inside JSON strings.

Return JSON in exactly this shape:
{{"page_number": {page_number}, "questions": [{{"raw_question_number": "3(a)", "question_text": "...", "question_type": "descriptive", "marks": 5, "section": "SECTION C: LONG ANSWER & WRITING SKILLS", "confidence": 0.9, "bbox": {{"x": 0, "y": 0, "width": 0, "height": 0}}}}]}}
question_type is one of: mcq, short_answer, descriptive, fill_blank, true_false, match, numerical, other."""


def answer_key_prompt(page_number: int, width: int, height: int) -> str:
    return f"""This image is page {page_number} of an official answer key / marking scheme ({width}x{height} pixels).
Adapt to any format (tabular marking schemes, point-by-point keys, solution manuals, model answers).
For every question that has an answer on this page, transcribe the answer and criteria exactly as written.

RULES:
1. "question_number" is the question label as written (e.g. "1", "Q1", "(1)", "3(a)", "4(i)", "(b)") or null if unlabelled. Never infer from ordering.
2. "answer_text" is the complete answer. Preserve lists, formulas, steps, chemical equations, and Markdown tables (| col1 | col2 |).
3. Mathematical notation: preserve exponents ((4/3)⁵ or 1024/243), steps, and formulas: (a + b)² = a² + b² + 2ab, A = P(1 - R1/100)(1 - R2/100).
4. Notice Writing & Formats: preserve notice structure and enclosing text borders.
5. CONTINUATIONS ACROSS PAGES: If an answer starts on one page and finishes on the next page, transcribe the continuation text completely with question_number null or matching the question (e.g. "Q4 cont"). NEVER split continuation points into separate questions.
6. "marks": Total marks for this question. If the marking scheme specifies individual criteria (e.g. "1 Mark: ...", "1 Mark: ..." -> 2 marks; "1.5 Marks: ...", "1.5 Marks: ..." -> 3 marks; "Marking Scheme (5 Marks Total)" -> 5 marks), calculate and set "marks" to the sum of the criteria or explicit question total. NEVER output the section total (like "10 Marks" or "12 Marks" from Section headings) as a question's marks.
7. "criteria": list of marking points or step allocations (e.g. ["1 Mark: Stating the purpose...", "1 Mark: Mentioning finding the letter..."]).
8. "accepted_answers": alternative acceptable answers if explicitly listed.
9. "keywords": keywords if explicitly listed.
10. "bbox" in image PIXELS (x, y, width, height) or null.

Return JSON in exactly this shape:
{{"page_number": {page_number}, "answers": [{{"question_number": "3(a)", "answer_text": "...", "marks": 5, "criteria": ["..."], "accepted_answers": [], "keywords": [], "confidence": 0.9, "bbox": null}}]}}"""


def student_answer_prompt(page_number: int, width: int, height: int, canonical_questions: list[str] | None = None) -> str:
    canonical_section = ""
    if canonical_questions:
        q_lines = "\n".join(f"- {q}" for q in canonical_questions)
        canonical_section = f"""CANONICAL_QUESTIONS (FOR QUESTION NUMBER MAPPING ONLY):
{q_lines}
IMPORTANT: These questions are listed ONLY so you can identify question numbers and map question IDs.
Under NO circumstances should the question text or outside knowledge be used to autocomplete, extend, or explain what the student wrote. Transcribe ONLY the ink strokes physically written by the student."""
    else:
        canonical_section = """CANONICAL_QUESTIONS (FOR QUESTION NUMBER MAPPING ONLY):
(Compare against verified examination questions registry; extract handwritten question numbers verbatim without inventing questions or completing answers)."""

    return f"""This image is page {page_number} of a student's handwritten answer sheet ({width}x{height} pixels).

You are the STUDENT ANSWER SHEET OCR, HANDWRITING UNDERSTANDING, ANSWER GROUPING, and QUESTION MAPPING engine for ADEM.

VISION MODEL:
Blaifa/InternVL3_5:4B

Your task is to read a student's actual handwritten answer sheet from the supplied page image and map each answer to the VERIFIED canonical question from the examination.

This is NOT normal text OCR.

You must understand:
- handwriting
- question numbers
- subquestion labels
- answer continuation
- page layout
- answer ordering
- crossed-out writing
- corrections
- tables
- mathematical calculations
- mathematical symbols
- formulas
- diagrams
- multi-line answers
- answers continuing across pages

==================================================
1. ABSOLUTE RULES
==================================================
NEVER invent a question number.
NEVER invent student text.
NEVER replace unreadable handwriting with a plausible sentence.
NEVER rewrite the student's answer into a different sentence.
NEVER use the official solutions or reference answers to fabricate what the student wrote.
NEVER assume OCR output is correct merely because it forms a grammatically valid sentence.
NEVER split one student's answer into multiple answers unless a genuine new question/subquestion is detected.
NEVER map an answer only because the OCR question number looks similar.
NEVER silently correct handwriting.
NEVER AUTOCOMPLETE INCOMPLETE ANSWERS: Students frequently write incomplete answers, forget explanations, or stop mid-sentence. You must STOP transcribing at the EXACT last visible handwritten pen stroke.
NEVER APPEND UNWRITTEN REASONS, FORMULAS, OR EXPLANATIONS: If the student wrote "no reaction occurs", you MUST transcribe ONLY "no reaction occurs" and STOP. NEVER append "because copper is less reactive than zinc", even if the question asked for a reason!
NEVER FINISH A STUDENT'S SENTENCE OR THOUGHT: Adding even a single unwritten word or clause is considered a critical hallucination and corrupts the grading evaluation.
CANONICAL_QUESTIONS ARE STRICTLY FOR NUMBER IDENTIFICATION: The question text is provided ONLY so you know which question ID to map to. NEVER use the question text, prompt instructions, or domain knowledge to generate, complete, or elaborate what the student wrote.
The image is the source of truth.

==================================================
2. CANONICAL QUESTION LIST
==================================================
{canonical_section}

==================================================
3. FIRST TASK — VISUAL READING
==================================================
Before mapping anything, inspect the actual handwritten image.
For every answer region determine:
- handwritten question label
- handwriting text
- line structure
- subquestion label
- continuation
- page location
- bounding box
The processing order MUST strictly be:
IMAGE -> VISUAL READING -> HANDWRITING OCR -> STRUCTURE -> ANSWER GROUPING -> QUESTION RESOLUTION -> CANONICAL MAPPING

==================================================
4. HANDWRITTEN QUESTION NUMBER RECOGNITION
==================================================
Question numbers are written in various student conventions:
- Numbers with angle bracket: '1>', '2>', '3>', '4>', '6>', '7>', '9>', '10>', 'a>', 'b>', 'c>'
- Numbers with comma, dot, colon, or parenthesis: '1)', '2.', '3:', 'Q1', 'Q.2', '1,', '2,'
- Question headers with copied topic titles and punctuation:
  e.g. 'Q1, force & pressure :', 'Q2, Sound wave Terminology :', 'Q3, Friction Types :',
       'Q4, Chemical Effects of Electric current.', 'Q5, optics & Reflection :',
       'Q6, Electrostatics & Natural phenomena :', 'Q7, Acoustics & noise pollution :'
  Always recognize the question number (e.g. "Q1", "Q2", "Q3", "1", "2") and transcribe the topic and answer text.
- Subquestion labels: '(a)', 'a)', 'a,', 'a>', '(b)', 'b)', 'b,', 'b>', '(c)', 'c>', 'c,'
- SKIPPED QUESTIONS: Students frequently skip questions they choose not to answer (e.g. answering Q1, Q2, Q3, Q4, Q6, Q7, Q9, Q10 while skipping Q5 and Q8). Always label each answer with the exact question number the student wrote ('6>', 'Q6'), NEVER shift or renumber questions sequentially!
Always preserve raw_question_label exactly as written (e.g. '1>', '9>', 'Q1, force & pressure :', 'a>').
Question numbers may also be poorly handwritten (e.g. Q1 misread as Q17 due to top hook).
Do NOT immediately assume false numbers. Store raw_ocr_label / raw_question_label = "1>", analyze visual shape, sequence, position, and answer content.
If visual evidence strongly indicates Q1:
normalized_question_label = "Q1", question_id = "q1", resolution_method = "handwriting_visual_correction".
Never erase raw OCR output.


==================================================
5. QUESTION NUMBER SEQUENCE
==================================================
Use document sequence as evidence combined with handwriting shape, answer content, and page position. Sequence alone is never enough.

==================================================
6. HANDWRITING OCR & UNCERTAINTY PRESERVATION
==================================================
Read actual handwriting character-by-character as accurately as possible.
Do NOT transform unclear handwriting into grammatically fluent fabrications.
When uncertain about a word, preserve uncertainty verbatim (e.g. "[unclear]" or "[UNCLEAR]").
Never hallucinate missing words.
VERBATIM STOPPING RULE (MANDATORY): Transcribe ONLY the visible ink strokes. If a student wrote half an answer or stopped mid-concept, transcribe ONLY the words that are physically on the page. Do NOT provide the rest of the answer, do NOT write the "because..." clause, and do NOT complete the explanation. The AI grading engine will evaluate what the student wrote, so adding unwritten text gives false marks to the student!

==================================================
7. USE THE ENTIRE HANDWRITTEN REGION & STYLE
==================================================
Read previous line, current line, and next line together. Use handwriting style consistency across the page to disambiguate strokes.

==================================================
8. MULTIPLE ANSWERS PER PAGE (MANDATORY)
==================================================
A single student answer sheet page ALMOST ALWAYS contains answers to MULTIPLE different questions.
YOU MUST:
- Scan the entire page thoroughly from the VERY TOP MARGIN to the bottom margin. Check the topmost area of the page first for any question number or answers (including reading comprehension, definitions, formulas, or short answers) before moving down the page. NEVER skip or omit answers written near the top margin!
- Identify EVERY question the student answered on this page.
- Create a SEPARATE entry in the "answers" array for EACH question (ans_001, ans_002, ans_003, ans_004, ...).
- NEVER lump multiple different questions together into a single answer!
- Distinguish between main question numbers and subparts: a digit followed by a bracket or dot (e.g. 7), 8), 9), 10>) indicates a new question; NEVER mistake a question number as a sub-part letter (such as mistaking handwritten 8) as d)). Question numbers 1-20 are separate questions.
- NEVER stop generating after the first answer! Keep scanning until the very bottom margin of the page.

==================================================
9. ANSWER CONTENT NUMBERING (CRITICAL)
==================================================
Content numbering inside an answer (such as 1), 2), 3), (i), (ii), (iii), or bullet points describing zones, reasons, types, steps) is PART OF THE ANSWER TEXT, NOT a new question!
Group all lines, points, and calculations under the active question.


==================================================
10. CONTINUATION RULE
==================================================
If no new question/subquestion marker appears, continue using current answer context.
Text continuing across page breaks without a new label belongs to the active answer.

==================================================
11. HANDWRITTEN CORRECTIONS & CROSSED-OUT TEXT
==================================================
Completely omit crossed-out, struck-through, or scribbled-out lines. Transcribe ONLY the student's visible final intended writing. Never transcribe struck-through words, and never invent corrected text.

==================================================
12. MATHEMATICAL & SCIENTIFIC ANSWERS
==================================================
Preserve powers (2³, x²), fractions (1/2), roots (√x), variables, equations, equal signs, negative signs, superscripts, subscripts, and LaTeX formulas.
Preserve scientific notation: chemical formulas (H₂O, CO₂, H₂SO₄), units (m/s²), etc.

==================================================
13. TABLE ANSWERS & DIAGRAMS
==================================================
- Preserve table rows, columns, and cells (format as Markdown tables).
- For student drawings, geometric figures, ray diagrams, circuits, and sketches: YOU MUST describe the visual drawing in detail inside `[Diagram: ...]`, including components, connections, arrow directions, axes, ray paths, and labels (e.g. `[Diagram: Convex lens with incident rays parallel to principal axis converging at focal point F; inverted real image labelled A'B']`). This allows the AI grading engine to award partial or full marks for required diagram features.

==================================================
14. QUESTION MAPPING PRIORITY
==================================================
Priority order:
1. Reliable handwritten question number
2. Question sequence
3. Physical location
4. Subquestion structure
5. Answer-content compatibility
6. Page continuity

==================================================
15. IMPORTANT — NEVER USE OFFICIAL SOLUTIONS OR QUESTION TEXT AS STUDENT OCR
==================================================
Official solutions and question descriptions must NEVER be used to replace, autocomplete, or fabricate what the student actually wrote. Student OCR and solution extraction are completely independent. Even if a student answer is scientifically incomplete or factually incorrect, transcribe strictly what is written without completing sentences or adding unwritten scientific justifications.

==================================================
16. CONFIDENCE & AUTOMATIC MAPPING POLICY
==================================================
Return distinct confidences: question_number_confidence, ocr_confidence, grouping_confidence, mapping_confidence.
mapping_status values:
- "MAPPED": All evidence agrees.
- "SUGGESTED": Strong evidence but handwritten number has visual ambiguity.
- "NEEDS_REVIEW": Multiple questions plausible.
- "UNMAPPED": No canonical question identified.

==================================================
17. UNIVERSAL TEXT FORMAT SUPPORT
==================================================
Support any language (English, Tamil, Hindi, bilingual, mathematics), paragraphs, headings, tables, formulas. Return what is actually in the image without summarisation or rewriting.

==================================================
OUTPUT FORMAT
==================================================
Return ONLY valid JSON in exactly this structure (include a separate entry in "answers" for EVERY question answered on this page):
{{
  "page_number": {page_number},
  "answers": [
    {{
      "answer_id": "ans_001",
      "question_number": "Q1",
      "raw_question_label": "1>",
      "normalized_question_label": "Q1",
      "question_id": "q1",
      "mapping_status": "MAPPED",
      "question_number_confidence": 0.95,
      "ocr_confidence": 0.95,
      "grouping_confidence": 0.98,
      "mapping_confidence": 0.96,
      "answer_text": "Complete transcribed handwritten text for this question...",
      "page_number": {page_number},
      "bbox": {{"x": 0, "y": 0, "width": 0, "height": 0}}
    }},
    {{
      "answer_id": "ans_002",
      "question_number": "Q2",
      "raw_question_label": "2>",
      "normalized_question_label": "Q2",
      "question_id": "q2",
      "mapping_status": "MAPPED",
      "question_number_confidence": 0.95,
      "ocr_confidence": 0.95,
      "grouping_confidence": 0.98,
      "mapping_confidence": 0.96,
      "answer_text": "Complete transcribed handwritten text for this question...",
      "page_number": {page_number},
      "bbox": {{"x": 0, "y": 0, "width": 0, "height": 0}}
    }}
  ],
  "unresolved": []
}}"""


EVAL_SYSTEM = (
    "You are a strict, fair examiner's assistant. Evaluate the student's answer ONLY against the official "
    "answer key and marking criteria provided. Do not reward information that is not in the student's answer. "
    "Do not use outside knowledge to award marks the key does not support. Do not penalise spelling or "
    "grammar unless the criteria say language accuracy matters. Never award more than the maximum marks.\n"
    "GRADING PRINCIPLES:\n"
    "1. Verifiable Calculations (NO Credit for Uncalculated Steps): In mathematics and numerical problems, NEVER award marks for final values or calculations that the student did NOT actually write. If a criterion awards marks for 'substituting and calculating A = Rs. 1,03,500', but the student only substituted into the formula and never calculated the value 1,03,500, award credit ONLY for the formula substitution (e.g. 0.5 - 1.0 mark) and NOT for the uncalculated numerical result. Mark uncalculated steps as missing.\n"
    "2. Strict Truth in Matched vs Missing Points: Every point listed in 'matched_points' MUST be physically and accurately present in the student's text. If the student wrote '8xy' instead of '48xy', DO NOT list 'Correctly simplified to 48xy' in matched_points! Accurately report 'Obtained 8xy instead of 48xy' under missing_points or feedback, and deduct marks for the error.\n"
    "3. Accurate Subpart Checking: Check the student answer carefully before listing an item as missing. If the student expanded '(3x - 4y)(3x + 4y)' into '9x^2 - 16y^2', DO NOT list that expansion as missing.\n"
    "4. Method and Step Credit with Arithmetic Checking: In mathematics and science, award proportional partial marks for correct formulas and principles. Verify that intermediate steps follow. Deduct only for a genuinely wrong step of reasoning (e.g. [64/3 x 64/81] = 1024/243 where the step does not hold), and only the marks of that step's criterion. A small slip whose working and final answer stay correct costs at most 0.5 marks.\n"
    "5. Multi-Part Questions: When a question or answer has multiple parts (e.g. (a), (b), (c) or 1), 2)), you must carefully inspect the student's text for EVERY part before concluding anything is missing. Never label a subpart as missing if the student wrote an answer for it.\n"
    "6. Run-On Steps & Space Delimiters: In mathematics and science, students frequently write calculations continuously or separated by spaces on a single line (e.g., '... 36 = x^2 + 2 + 1/x^2 x^2 + 1/x^2 = 34'). Read the entire student answer string completely to the end before deciding whether a step or final answer is present.\n"
    "7. Case and Punctuation Tolerance: Do not penalize capitalization differences (e.g., 'Book' instead of 'book') unless letter case is specifically being tested in the criteria.\n"
    "8. Diagrams: When evaluating answers containing `[Diagram: ...]`, award criteria marks based on whether the required components, ray paths, connections, or labels are documented in the diagram description.\n"
    "9. Text marked [UNCLEAR] could not be read; do not assume what it said.\n"
    "FAIR MARKING (as a reasonable teacher would):\n"
    "10. Every deduction must name the specific marking criterion or answer-key point that is missing or wrong in 'missing_points'. If you cannot name one, award full marks for that part.\n"
    "11. Never deduct for correct extra information the question did not ask for (e.g. a balanced equation alongside a word equation, naming the anode as well as the cathode). Deduct only if the extra content is wrong or contradicts the answer.\n"
    "12. Accept equivalent notation and wording: x, × and * for multiplication; ^2 and ²; 'Hz' and 'hertz'; synonyms and paraphrases with the same meaning. Do not require details, laws or terms that are not in the answer key.\n"
    "13. The student answer is an OCR transcription of handwriting. A stray or swapped character (e.g. '3001' where the working clearly continues with 300) is most likely a reading error: do not deduct for it when the surrounding working is consistent; mention it in feedback instead.\n"
    "14. Tamil and other Indian languages: compare meaning, not exact words. Accept different case endings, sandhi joins, spelling variants and synonyms (e.g. 'திருக்குறள்' / 'திருக்குறளை'). Write matched_points, missing_points and feedback in the language of the answer key.\n"
    "Reply with a single JSON object and nothing else."
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

Award marks between 0 and {max_marks:g} (decimals allowed in 0.5 steps). Check all subparts ((a), (b)) and read the full student answer to the end before marking anything missing.
GRADING RULES:
1. Do NOT award marks for calculations the student did not write. If student wrote only the formula and stopped without computing, award partial mark ONLY for formula substitution and mark the calculation missing.
2. Every item in matched_points MUST be truthfully written by the student. If student wrote '8xy', do NOT claim student obtained '48xy'.
3. Award proportional step marks for correct method/formula. Deduct only the marks of a criterion that is missing or genuinely wrong, and list it in missing_points; a minor slip with correct working and answer costs at most 0.5.
4. Do not deduct for correct extra information, equivalent notation, or likely handwriting-reading errors.
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



IDENTITY_SYSTEM = (
    "You read the student details box on the first page of a handwritten examination answer sheet. "
    "Transcribe only what is written; never guess a character you cannot read. Reply with a single valid JSON object and nothing else."
)


def student_identity_prompt() -> str:
    return """This image is the top of the first page of a student's answer sheet.
Find the student's details, usually written in a header box or on labelled lines such as
"Name", "Roll No", "Roll Number", "Reg No", "Register Number", "Registration No", "Class", "Std", "Section", "Sec".

RULES:
- Copy each value exactly as written (keep letters, digits, slashes and dashes). Do not reformat or complete it.
- The value is what is written AFTER the label. Never return the label itself (e.g. "Roll no", "Reg. No") as a value.
- The photo may be rotated or the details may be in the middle of the page; read them wherever they are.
- A roll number and a registration number are different fields; only fill each from its own label.
- If a value is missing, crossed out or not clearly legible, use null.
- Ignore the exam name, subject, date, school name and any printed instructions.

Return JSON in exactly this shape:
{"name": "...", "roll_number": "...", "registration_number": "...", "class_name": "...", "section": "..."}"""


LABELER_SYSTEM = (
    "You are the labeling assistant for ADEM, an exam evaluation system. Questions, answers and keys may be in "
    "Tamil, another Indian language, or English. You label what is already written: never invent questions, "
    "answer content, marks, or points that are not in the text. Reply with a single valid JSON object and nothing else."
)


def question_type_label_prompt(items: list[dict]) -> str:
    lines = "\n\n".join(f"ID: {it['id']} (marks: {it['marks'] if it['marks'] is not None else 'unknown'})\n{it['text']}"
                        for it in items)
    return f"""Classify each exam question below by what kind of answer it asks for.

TYPES:
- mcq: choose one of the given options
- fill_blank: fill a gap in a sentence
- true_false: say whether a statement is true or false
- match: match items of one list with another
- numerical: calculate a number
- short_answer: a word, phrase or one or two sentences (definitions, naming, "who/what/when", short explanations)
- descriptive: a paragraph or longer answer (explain in detail, describe, essay, letter, compare, discuss)
- other: none of the above (e.g. draw a diagram, recite a poem)

Use the question wording first; use the marks only to break a tie between short_answer and descriptive.

QUESTIONS:
{lines}

Return JSON in exactly this shape, one entry per ID:
{{"labels": [{{"id": "...", "question_type": "short_answer"}}]}}"""


def criteria_label_prompt(items: list[dict]) -> str:
    lines = "\n\n".join(f"ID: {it['id']} (total marks: {it['marks']:g})\nQUESTION: {it['question'] or '(not available)'}\n"
                        f"OFFICIAL ANSWER:\n{it['answer']}" for it in items)
    return f"""Split each official answer below into marking points, the way an examiner would award marks.

RULES:
1. Every point must state something that is written in the OFFICIAL ANSWER. Do not add facts, steps or explanations.
2. Write each point in the same language as the official answer, short (one idea per point).
3. Give each point its marks. The marks of an ID's points must add up EXACTLY to its total marks (0.5 steps allowed).
4. If the answer is a single fact worth all the marks, return one point with the full marks.

ANSWERS:
{lines}

Return JSON in exactly this shape, one entry per ID:
{{"keys": [{{"id": "...", "criteria": [{{"point": "...", "marks": 1}}]}}]}}"""
