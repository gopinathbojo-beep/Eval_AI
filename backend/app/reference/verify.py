"""Checks answers (AI-generated or teacher-saved) against the reference library. No AI is involved.

The books and marking schemes are the authority and are shown exactly as printed; nothing here rewrites or
judges them. The check finds the NCERT / marking-scheme passages for the question, measures how much of the
answer they contain, and flags numbers no passage has and citations the answer was not given. The teacher reads
the passage and decides: word overlap shows an answer is on the topic, not that it is right ("photosynthesis is
done by animals" shares its words with the chapter).

Statuses:
  ON_TOPIC      the passages found cover the answer's words; compare with the book text shown
  PARTIAL       some do, or the answer has numbers no source has, or it cites no source
  UNSUPPORTED   the passages found say little of what the answer says
  NO_REFERENCE  nothing in the library matches the question (Tamil, or a topic outside NCERT)
  NOT_CHECKED   too short to check by words (an MCQ option); compare with the book text shown"""
import re
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from .search import Hit, coverage, query_terms, search

SUPPORTED_AT, PARTIAL_AT = 0.6, 0.35
BOARD_MATCH_AT = 0.7
# computed answers legitimately hold numbers the book never prints
_NUMERIC = ("mathematics", "physics", "chemistry", "accountancy", "economics", "computer", "informatics")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
_MESSAGES = {
    "ON_TOPIC": "The textbook / marking scheme covers this: compare the answer with the book text shown.",
    "PARTIAL": "Only partly found in the textbook / marking scheme: check against the book text shown.",
    "UNSUPPORTED": "Not found in the textbook / marking scheme passages: check carefully.",
    "NO_REFERENCE": "No source found in the reference library: check carefully.",
    "NOT_CHECKED": "Too short to check by words: compare with the book text shown.",
}


@dataclass
class Verification:
    status: str
    message: str
    support: float = 0.0
    sources: list[dict] = field(default_factory=list)  # each with the passage exactly as printed
    board_match: dict | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def label_sources(hits: list[Hit]) -> list[dict]:
    return [{"label": f"S{i}", "title": h.title, "chapter": h.chapter, "pages": _pages(h), "kind": h.kind,
             "question_number": h.question_number, "score": h.score, "text": h.text}
            for i, h in enumerate(hits, 1)]


def _pages(h: Hit) -> str:
    return str(h.page_start) if h.page_start == h.page_end else f"{h.page_start}-{h.page_end}"


def find_references(db: Session, standard: int, subject: str, question: str, k: int = 3) -> list[Hit]:
    """Passages for one question, looked up by the question text alone so they are the same for every answer."""
    return search(db, question, standard, subject, k=k, min_match=0.4)


def verify_answer(db: Session, standard: int, subject: str, question: str, answer: str,
                  references: list[Hit] | None = None, cited: list[str] | None = None) -> Verification:
    """cited = source labels the generator said it used (None for a teacher's answer)."""
    return _word_check(db, standard, subject, question, answer, references, cited)[0]


def verify_answers(db: Session, standard: int, subject: str, items: list[dict]) -> list[Verification]:
    """items: [{question, answer, references?, cited?}]."""
    return [verify_answer(db, standard, subject, it["question"], it["answer"], it.get("references"), it.get("cited"))
            for it in items]


def _word_check(db, standard, subject, question, answer, references, cited) -> tuple[Verification, list[Hit]]:
    refs = list(references) if references is not None else find_references(db, standard, subject, question)
    extra = search(db, f"{question} {answer}", standard, subject, k=3, min_match=PARTIAL_AT)
    seen = {h.chunk_id for h in refs}
    refs += [h for h in extra if h.chunk_id not in seen]
    if not refs:
        return Verification("NO_REFERENCE", _MESSAGES["NO_REFERENCE"]), refs
    sources, board = label_sources(refs), _board_match(refs, question)
    notes = []
    if board:
        notes.append(f"Same question as {board['source']} Q{board['question_number']}: compare with the board answer.")
    terms = query_terms(answer)
    if len(terms) < 2:
        return Verification("NOT_CHECKED", _MESSAGES["NOT_CHECKED"], sources=sources, board_match=board, notes=notes), refs
    corpus = "\n".join(h.text for h in refs)
    support = round(coverage(terms, corpus), 3)
    status = "ON_TOPIC" if support >= SUPPORTED_AT else "PARTIAL" if support >= PARTIAL_AT else "UNSUPPORTED"
    if not any(k in subject for k in _NUMERIC):
        missing = [n for n in dict.fromkeys(_NUMBER.findall(answer))
                   if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", corpus)]
        if missing:
            notes.append("Numbers not found in any source: " + ", ".join(missing[:8]) + ".")
    if cited is not None:
        given = {s["label"] for s in sources}
        unknown = [c for c in cited if c not in given]
        if unknown:
            notes.append("Cites sources it was not given: " + ", ".join(unknown) + ".")
        if not [c for c in cited if c in given]:
            notes.append("The answer cites no source.")
    if status == "ON_TOPIC" and any(not n.startswith("Same question") for n in notes):
        status = "PARTIAL"
    return Verification(status, _MESSAGES[status], support, sources, board, notes), refs


_BOARD = re.compile(r"^QUESTION (?P<n>\S+): (?P<question>.*?)\nMARKING SCHEME: (?P<answer>.*)$", re.S)


def board_answer(refs: list[Hit], question: str) -> dict | None:
    """The CBSE sample-paper question this is, with its marking-scheme answer exactly as printed.
    The question texts must match both ways (each holds BOARD_MATCH_AT of the other's words), so a different
    question on the same topic is not taken for it."""
    terms = query_terms(question)
    if len(terms) < 3:
        return None
    for h in refs:
        m = _BOARD.match(h.text) if h.kind == "MARKING_SCHEME" and h.question_number else None
        # an "attempt either A or B" question may be asked as one option alone
        parts = [m["question"]] + re.split(r"\n(?:OR\n)?(?=[A-D]\. )", m["question"])[1:] if m else []
        if any(coverage(terms, p) >= BOARD_MATCH_AT and coverage(query_terms(p), question) >= BOARD_MATCH_AT
               for p in parts):
            answer = re.sub(rf"^{re.escape(m['n'])}\s+", "", m["answer"])  # the row's question-number column
            return {"source": h.title, "question_number": h.question_number, "marks": h.marks,
                    "question": m["question"], "answer": answer, "pages": _pages(h), "text": h.text}
    return None


def _board_match(refs: list[Hit], question: str) -> dict | None:
    b = board_answer(refs, question)
    return {k: b[k] for k in ("source", "question_number", "marks", "text")} if b else None


def find_board_answer(db: Session, standard: int, subject: str, question: str) -> dict | None:
    """board_answer over a search of the marking schemes alone, so textbook pages cannot crowd them out."""
    return board_answer(search(db, question, standard, subject, kinds=["MARKING_SCHEME"], k=5, min_match=0.4), question)
