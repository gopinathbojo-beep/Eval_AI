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
lower so the teacher checks it, and say why in feedback. Start feedback with the kind, e.g. "[Comprehension] ...".
EVIDENCE: marking by meaning never changes how you quote. Every mark you give needs evidence_quotes copied
EXACTLY, character for character, from the student's answer: the student's own words that carry the idea, never your
paraphrase, a corrected spelling or the scheme's wording. For an implied idea, quote the words it is implied by. If
there are no such words in the student's answer, that idea earns nothing."""


def language_rules(question_text: str | None, key_text: str | None) -> str:
    return LANGUAGE_RULES


THEORY_RULES = """UNDERSTANDING-BASED MARKING RULES. First decide which kind each scheme point is, then mark it so:
1. EXPLANATION (explain, why, describe, give reasons, distinguish, state the importance): split each scheme point into
   its ideas. For each idea: full credit when the student's answer clearly means it, in any wording; partial credit when
   the idea is only implied or could be read another way; zero when it is missing or wrong.
2. FACT (a definition, law, named term, date, place, person, formula, chemical name, label of a diagram): it must be
   correct as the textbook and scheme give it. A wrong or different fact earns nothing; wording around it may differ.
3. NUMERICAL OR DERIVATION WORKING: mark by the scheme's steps exactly as given; these rules change nothing there.
Do not deduct for spelling or grammar slips unless the scheme says so, or unless a misspelling changes the term
(e.g. a different chemical or person). When you give partial credit for an implied idea, or you are unsure, set
confidence to 0.5 or lower so the teacher checks it, and say why in feedback.
EVIDENCE: marking by meaning never changes how you quote. Every mark you give needs evidence_quotes copied
EXACTLY, character for character, from the student's answer: the student's own words that carry the idea, never your
paraphrase, a corrected spelling or the scheme's wording. For an implied idea, quote the words it is implied by. If
there are no such words in the student's answer, that idea earns nothing."""


def theory_rules(question_text: str | None, key_text: str | None) -> str:
    return THEORY_RULES
