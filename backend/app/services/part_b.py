"""Which Part B option a student answered, decided once for the whole sheet: a student attempts only one option, so
their answers to Q27..Q34 are all marked against it. One small-model call, only for papers with options. When it cannot
be decided the choice is left open and each question is marked against whichever option its answer earns most on."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..cbse.extraction import BRANCHES, BRANCH_TITLES, has_branches, option_text
from ..config import get_settings
from ..models import Evaluation, Exam, StudentAnswer
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured
from .mapping_service import exam_questions

log = logging.getLogger("adem.part_b")

SYSTEM = "You read a student's exam answers and say which optional part of the paper they answered. Reply with JSON only."


class OptionChoice(BaseModel):
    model_config = {"extra": "ignore"}
    option: str | None = None


def _flat(text: str | None, limit: int) -> str:
    return re.sub(r"\s+", " ", text or "")[:limit]


def build_prompt(questions: list, answers: dict[str, str], other: list[str]) -> str:
    lines = []
    for q in questions:
        if q.id not in answers:
            continue
        lines.append(f"Q{q.display_number}")
        lines += [f"  {b}: {_flat(option_text(q.question_text, b), 220)}" for b in BRANCHES]
        lines.append(f"  STUDENT WROTE: {_flat(answers[q.id], 400)}")
    written = ("\n\nOTHER TEXT ON THE SHEET\n" + "\n".join(other)) if other else ""
    return ("Part B of this paper has two options with the same question numbers: "
            f"financial ({BRANCH_TITLES['financial']}, Option I) and computerised ({BRANCH_TITLES['computerised']}, "
            "Option II). A student answers one.\n\n" + "\n".join(lines) + written +
            "\n\nThe option the student names in writing (\"Option II\", \"Computerised Accounting\") is the strongest "
            "evidence; otherwise judge from which option's questions the answers address. If the student wrote answers "
            "for both options, give the one with more answers. Give null only when it cannot be told.\n\n"
            'Reply: {"option": "financial"}')


def student_option(db: Session, ev: Evaluation, ask=None) -> str | None:
    exam = db.get(Exam, ev.exam_id)
    if (exam.standard_options or {}).get("accountancy_option"):
        return None   # an older exam marked against one option for everybody
    questions = [q for q in exam_questions(db, ev.exam_id) if has_branches((q.structure or {}).get("tree"))]
    if not questions:
        return None
    ids = {q.id for q in questions}
    rows = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    answers: dict[str, str] = {}
    for a in rows:
        if a.exam_question_id in ids and a.status != "IGNORED":
            answers[a.exam_question_id] = f"{answers.get(a.exam_question_id, '')} {a.answer_text or ''}".strip()
    if not answers:
        return None   # no Part B on this sheet
    other = [_flat(a.answer_text, 80) for a in rows if a.status == "IGNORED" and len(a.answer_text or "") <= 80]
    prompt = build_prompt(questions, answers, other)
    db.commit()   # the AI call must not hold the database's write lock
    try:
        if ask is not None:
            reply = ask(SYSTEM, prompt)
        else:
            reply = chat_structured(SYSTEM, prompt, OptionChoice, model=get_settings().small_model).parsed
    except (AIResponseError, AIUnavailable) as e:
        log.warning("Part B option of evaluation %s not decided: %s", ev.id, getattr(e, "detail", e))
        return None
    option = (reply.option or "").strip().lower()
    return option if option in BRANCHES else None
