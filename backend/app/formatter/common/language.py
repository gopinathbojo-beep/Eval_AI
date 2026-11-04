"""Understanding-based marking rules, used only by the grader in evaluation (Marks & Finalize); reading papers,
keys and sheets never use them. LANGUAGE_RULES: English, Tamil, Hindi. THEORY_RULES: descriptive answers in every
other subject except Maths (Science, Social Science, Biology, ...)."""

LANGUAGE_RULES = """LANGUAGE MARKING RULES (this is a language paper). First decide which kind this question is, then mark it so:
1. READING COMPREHENSION (an unseen passage printed in the question paper): split each scheme point into its ideas.
   For each idea: full credit when the student's answer clearly means it, in any wording; partial credit when the idea
   is only implied or could be read another way; zero when it is missing or contradicts the passage. Judge against the
   passage printed with the question.
2. LITERATURE (a lesson or poem from the textbook): mark EXACTLY against the textbook and the scheme. Names, events,
   facts, characters and reasons must be the ones the textbook lesson gives; content the lesson does not support earns
   nothing. A quoted poem line or line from the lesson must be word for word. Do not credit a loose interpretation.
   For literature this replaces the general textbook-reference rule: here the textbook passages are the standard.
3. GRAMMAR (fill in the blank, transformation, voice, reported speech, error correction): exact word or form only.
4. WRITING (letter, notice, essay, article, diary, speech): mark by the scheme's band criteria (format, content,
   expression) as given.
Do not deduct for spelling or grammar slips in a content answer (comprehension or literature) unless the scheme says so.
When you give partial credit for an implied idea, or you are unsure which kind the question is, set confidence to 0.5 or
lower so the teacher checks it, and say why in feedback. Start feedback with the kind, e.g. "[Comprehension] ..."."""


def language_rules(question_text: str | None, key_text: str | None) -> str:
    return LANGUAGE_RULES


THEORY_RULES = """UNDERSTANDING-BASED MARKING RULES. First decide which kind each scheme point is, then mark it so:
1. EXPLANATION (explain, why, describe, give reasons, distinguish, state the importance): split each scheme point into
   its ideas. For each idea: full credit when the student's answer clearly means it, in any wording, even briefly;
   partial credit when the idea is only implied, incomplete or loosely worded; zero only when it is absent, wrong or
   the opposite of the key.
2. FACT (a definition, law, named term, date, place, person, formula, chemical name, label of a diagram): it must be
   correct as the textbook and scheme give it. A wrong or opposite fact earns nothing; wording around it may differ, and
   a definition that gets the essential idea right earns its marks.
3. NUMERICAL, JOURNAL OR DERIVATION WORKING: mark by the scheme's steps; each step or entry that is right, or partly
   right (correct accounts with a wrong amount, a correct formula with an arithmetic slip), earns its share.
4. Several attempts or struck-out versions in one answer: the attempt that best matches the key counts; the others are
   ignored.
Do not deduct for spelling or grammar slips unless the scheme says so, or unless a misspelling changes the term
(e.g. a different chemical or person). When you give partial credit for an implied idea, or you are unsure, set
confidence to 0.5 or lower so the teacher checks it, and say why in feedback."""


def theory_rules(question_text: str | None, key_text: str | None) -> str:
    return THEORY_RULES
