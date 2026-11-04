"""DB-aware wrappers around the pure mapping rules."""
from __future__ import annotations
from typing import Any
import re
from sqlalchemy.orm import Session
from .. import formatter
from ..config import get_settings
from ..models import AnswerKey, Evaluation, ExamQuestion, StudentAnswer
from ..formatter.common.mapping import MAPPED, NEEDS_REVIEW, UNMAPPED, flag_duplicates, map_label, detect_mapping_anomalies
from ..formatter.common.numbering import part_labels, normalize_question_number, parent_number

DUP_NOTE = "DUPLICATE_MAPPING: another answer also maps to this question"
_RECOMPUTABLE = {"UNMAPPED", "NEEDS_REVIEW", "MAPPED"}


def conflicting_answer_heading(text: str, number: str | None) -> str | None:
    """An explicit Qn / n> header is evidence; numbered working steps are not."""
    expected = re.match(r"\d+", number or "")
    if not expected:
        return None
    for line in [line.strip() for line in text.splitlines() if line.strip()][:4]:
        if re.match(r"^section\b", line, re.I):
            continue
        heading = re.match(r"^(?:Q(?:uestion)?\s*\.?\s*(\d+)(?=\W|$)|(\d+)\s*>)", line, re.I)
        root = (heading[1] or heading[2]) if heading else None
        return root if root and root != expected[0] else None
    return None


def exam_questions(db: Session, exam_id: str) -> list[ExamQuestion]:
    return db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position).all()


def apply_student_mapping(db: Session, ev: Evaluation) -> None:
    qs = exam_questions(db, ev.exam_id)
    minc = get_settings().min_label_confidence
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    cbse_roots = {q.normalized_number:q for q in qs if getattr(q,"structure",None)}
    total_ans = len(answers)
    in_part = dict(zip((a.id for a in answers), part_labels(answers, qs)))
    prev_qid = None
    suggested: list[tuple[StudentAnswer, list[dict]]] = []  # unlabelled answers placed by content alone
    for a in answers:
        conflict = conflicting_answer_heading(a.answer_text or "", a.normalized_number or a.raw_question_number)
        if conflict and a.status in _RECOMPUTABLE:
            candidate = next((q for q in qs if q.normalized_number == conflict), None)
            a.status = "NEEDS_REVIEW"
            a.mapping_note = f"The answer text starts with question {conflict}, conflicting with its extracted label. Review the mapping."
            a.mapping_candidates = [candidate.id] if candidate else []
            continue
        if a.status == "IGNORED" or a.status not in _RECOMPUTABLE:
            if a.exam_question_id:
                prev_qid = a.exam_question_id
            continue
        if a.mapping_confirmed and a.exam_question_id:
            a.status, a.mapping_note, a.mapping_candidates = "MAPPED", None, []
            prev_qid = a.exam_question_id
            continue
        continuation = re.fullmatch(r"Source grouping: continuation of question (\d+)", a.mapping_note or "")
        root = cbse_roots.get(continuation[1]) if continuation else None
        if root and a.normalized_number and prev_qid == root.id:
            a.exam_question_id, a.normalized_number = root.id, root.normalized_number
            a.status, a.mapping_candidates = "MAPPED", []
            prev_qid = root.id
            continue
        if not a.raw_question_number and a.normalized_number in cbse_roots:
            from ..formatter.common.answers import _math_question
            if _math_question(a.answer_text or "", qs) == a.normalized_number:
                root = cbse_roots[a.normalized_number]
                a.exam_question_id, a.status = root.id, "MAPPED"
                a.mapping_note, a.mapping_candidates = "Matched distinctive equations in the uploaded question", []
                prev_qid = root.id
                continue
        res = map_label(
            in_part.get(a.id) or a.raw_question_number,
            qs,
            a.ocr_confidence,
            minc,
            answer_text=a.answer_text,
            answer_position=a.position,
            total_answers=total_ans,
            prev_question_id=prev_qid,
        )
        if cbse_roots and a.raw_question_number and (a.ocr_confidence or 0) >= minc:
            from ..formatter.common.numbering import normalize_question_number
            label = normalize_question_number(a.raw_question_number) or ""
            match = re.match(r"^(\d+)(?:$|[.(])",label)
            root = cbse_roots.get(match.group(1)) if match else None
            if root:
                a.normalized_number,a.exam_question_id = label,root.id
                a.status,a.mapping_note,a.mapping_candidates = "MAPPED","Part of whole CBSE question",[]
                prev_qid = root.id
                continue
        a.normalized_number = res.normalized_number
        a.exam_question_id = res.question_id
        a.mapping_note = res.note
        a.mapping_candidates = res.candidates
        a.status = {MAPPED: "MAPPED", NEEDS_REVIEW: "NEEDS_REVIEW", UNMAPPED: "UNMAPPED"}[res.status]
        if res.question_id:
            prev_qid = res.question_id
        if not a.raw_question_number and res.status == NEEDS_REVIEW and res.question_id and res.candidate_details:
            suggested.append((a, res.candidate_details))
    _spread_content_suggestions(answers, qs, suggested)
    if cbse_roots:
        _repair_misread_labels(answers, qs)
    live = [a for a in answers if a.status != "IGNORED"]
    dups = flag_duplicates(live)
    dups -= {q.id for q in cbse_roots.values()}  # Whole questions intentionally contain several answer blocks.
    for a in live:
        if a.exam_question_id in dups and a.status in _RECOMPUTABLE:
            a.status, a.mapping_note = "NEEDS_REVIEW", DUP_NOTE
        elif a.status == "NEEDS_REVIEW" and (a.mapping_note or "").startswith("DUPLICATE_MAPPING"):
            a.status, a.mapping_note = "MAPPED", None
    _confirm_content_mappings(live, qs, suggested)
    _accept_confident_suggestions(live, qs)
    db.flush()


SURE_SUGGESTION = 0.7  # a suggested question this sure is taken without asking the teacher


def _accept_confident_suggestions(answers, qs) -> None:
    """Only an answer that fits no question is left for the teacher. A written number that matches a question but was
    read with low confidence, an answer placed on a question already answered, and a suggestion the content supports
    with at least SURE_SUGGESTION are mapped as suggested."""
    from ..formatter.common.recovery import find_recovery_candidates
    for a in answers:
        if a.status != "NEEDS_REVIEW" or a.mapping_confirmed:
            continue
        note = a.mapping_note or ""
        target = a.exam_question_id
        if not target:
            found = find_recovery_candidates(a.raw_question_number, a.answer_text, qs)
            if found and found[0].score >= SURE_SUGGESTION:
                target = next((q.id for q in qs if q.normalized_number == found[0].normalized_number), None)
        elif not (note.startswith("Exact label match") or note.startswith("DUPLICATE_MAPPING")):
            found = find_recovery_candidates(a.raw_question_number, a.answer_text, qs)
            top = next((q.id for q in qs if found and q.normalized_number == found[0].normalized_number), None)
            if not (found and found[0].score >= SURE_SUGGESTION) and top != target:
                # the content does not back the suggestion strongly: the best supported question, when sure enough
                target = top if found and found[0].score >= SURE_SUGGESTION else target
        if target:
            a.exam_question_id, a.status, a.mapping_note, a.mapping_candidates = target, "MAPPED", None, []


_OPTION_FIRST = re.compile(r"^\s*(?:Q?\s*\d{1,3}\s*[.):]?\s*)?\(?([A-Da-d])\)?(?=[.):\s]|$)")
_OPTIONS = re.compile(r"\(?\b([A-D])[.)]\s*(.+?)(?=\s+\(?[A-D][.)]\s|$)", re.S)


def _squash(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").casefold())


def _chooses_option(q: ExamQuestion, text: str | None) -> bool:
    """The answer opens with an option letter ("C. [NiCl₄]²⁻ ...", "B. 32 min") or names one of the question's
    options: it is this one-mark question's own answer, even when an explanation makes it long."""
    if _OPTION_FIRST.match(text or ""):
        return True
    answer = _squash((text or "")[:200])
    return any(len(_squash(o)) >= 4 and _squash(o) in answer
               for _, o in _OPTIONS.findall(q.question_text or ""))


def _opens_with_number(text: str | None, number: str | None = None) -> bool:
    match = re.match(r"\s*(?:Q\.?\s*)?(\d{1,3})\s*[.):]", text or "")
    return bool(match) and (number is None or match[1] == str(number))


def _continues(prev, a, before: ExamQuestion) -> bool:
    """Same page, and either the next numbered part of the question above ("17A 1. ..." then "2. ...") or plain
    text with no number or option of its own, which is the previous answer's explanation."""
    if prev.page_number != a.page_number:
        return False
    label = normalize_question_number(getattr(a, "raw_question_number", None))
    if label and not label.startswith("(") and parent_number(label).isdigit():
        return False  # A separate numbered answer is not the preceding answer's explanation.
    if _opens_with_number(a.answer_text, "2"):
        return not _is_one_mark(before) and re.search(r"(?:^|\s)1\s*[.)]", prev.answer_text or "") is not None
    return not _opens_with_number(a.answer_text) and not _OPTION_FIRST.match(a.answer_text or "")


def _is_one_mark(q: ExamQuestion) -> bool:
    return (q.question_type or "").lower() == "mcq" or (q.max_marks is not None and q.max_marks <= 1)


def _repair_misread_labels(answers: list, qs: list) -> None:
    """Fix the number the model read for an answer when the sheet itself shows it was misread.

    1. The student's own heading inside the answer ("36>", "Q36") beats a misread label, if 36 has no other answer.
    Repeated answers and rough working can share a question number. A known
    numeric label must not be reassigned merely because the answer is long.
    Only free questions are used; anything still unclear stays NEEDS_REVIEW for the teacher.
    """
    by_num = {q.normalized_number: q for q in qs if q.normalized_number}
    by_id = {q.id: q for q in qs}
    live = [a for a in answers if a.status in _RECOMPUTABLE]

    def taken(qid, but):
        return any(x is not but and x.exam_question_id == qid and x.status != "IGNORED" for x in answers)

    def move(a, q, note):
        a.exam_question_id, a.normalized_number = q.id, q.normalized_number
        a.status, a.mapping_note, a.mapping_candidates = "MAPPED", note, []

    for a in live:  # 1. the student's own heading
        heading = conflicting_answer_heading(a.answer_text or "", a.normalized_number or a.raw_question_number)
        target = by_num.get(heading) if heading else None
        if target and not taken(target.id, a):
            move(a, target, f"The answer starts with the student's heading {heading}; mapped to Q{heading}.")
    ordered = sorted(live, key=lambda x: x.position or 0)
    # Repeated numbers can be rough working or another attempt. Answer order
    # alone cannot establish a new question number.
    for prev, a in zip(ordered, ordered[1:]):  # a part or explanation the student wrote under the previous answer
        q, before = by_id.get(a.exam_question_id), by_id.get(prev.exam_question_id)
        if not (q and before and q.id != before.id and _is_one_mark(q) and taken(q.id, a)):
            continue
        if not _chooses_option(q, a.answer_text) and _continues(prev, a, before):
            move(a, before, f"Written under Q{before.normalized_number} with no number of its own; "
                            f"kept with Q{before.normalized_number}.")
    numbered = {}
    for a in ordered:
        q = by_id.get(a.exam_question_id)
        if q and _is_one_mark(q) and _opens_with_number(a.answer_text, q.normalized_number):
            numbered[q.id] = a
    for a in ordered:  # the sheet prints this number on another answer, so this one's number was misread
        q = by_id.get(a.exam_question_id)
        if (q and numbered.get(q.id) not in (None, a) and not _opens_with_number(a.answer_text)
                and not (a.mapping_note or "").startswith("Written under")):
            a.status = "NEEDS_REVIEW"
            a.mapping_note = (f"Read as Q{q.normalized_number}, but another answer is numbered "
                              f"{q.normalized_number} on the sheet. Choose the question for this answer.")
            a.mapping_candidates = [x.id for x in qs if _is_one_mark(x) and not taken(x.id, a)][:3]
    for a in ordered:  # 3. long working on an already-answered one-mark question
        q = by_id.get(a.exam_question_id)
        label = normalize_question_number(getattr(a, "raw_question_number", None))
        if q and label and parent_number(label) == q.normalized_number:
            continue
        if (a.mapping_note or "").startswith("Written under") or "numbered" in (a.mapping_note or ""):
            continue  # settled by the two steps above
        if not (q and _is_one_mark(q) and len((a.answer_text or "").strip()) > 120 and taken(q.id, a)):
            continue
        if _chooses_option(q, a.answer_text):
            continue  # it answers this question (an option and its explanation): it stays; the other piece moves
        res = map_label(None, [x for x in qs if not _is_one_mark(x)], answer_text=a.answer_text)
        details = sorted(res.candidate_details or [], key=lambda d: -(d.get("score") or 0))
        top = details[0] if details else None
        runner = details[1].get("score") or 0 if len(details) > 1 else 0
        best = by_id.get(top["id"]) if top else None
        score = top.get("score") or 0 if top else 0
        # a clear winner, or the only question its working matches at all (a continuation of a whole question)
        if best and ((score >= AUTO_MIN_SCORE and score - runner >= AUTO_MARGIN) or (len(details) == 1 and score >= .6)):
            move(a, best, f"Read as Q{q.normalized_number}, which is a one-mark question already answered; "
                          f"the working matches Q{best.normalized_number}.")
        else:
            a.status = "NEEDS_REVIEW"
            a.mapping_note = (f"Read as Q{q.normalized_number}, a one-mark question already answered; "
                              "this longer working belongs to another question.")
            a.mapping_candidates = [d["id"] for d in details[:3]]


AUTO_MIN_SCORE = 0.75
AUTO_MARGIN = 0.15


def _confirm_content_mappings(answers: list, qs: list, suggested: list[tuple[Any, list[dict]]]) -> None:
    """Map an unlabelled answer without review when every piece of evidence agrees: a strong content match that
    clearly beats any other question, no other answer on that question, and its place in the answer order (between
    the questions confidently answered before and after it). Anything short of that stays NEEDS_REVIEW."""
    qpos = {q.id: q.position for q in qs}
    for a, det in sorted(suggested, key=lambda x: x[0].position or 0):
        if a.status != "NEEDS_REVIEW" or not det or a.exam_question_id != det[0].get("id"):
            continue  # a duplicate, or moved by _spread_content_suggestions: the teacher decides
        top = det[0].get("score") or 0
        runner = max((d.get("score") or 0 for d in det[1:] if d.get("num") != det[0].get("num")), default=0)
        if top < AUTO_MIN_SCORE or top - runner < AUTO_MARGIN:
            continue
        if any(x is not a and x.exam_question_id == a.exam_question_id for x in answers):
            continue
        confident = [x for x in answers if x.status == "MAPPED" and x.exam_question_id in qpos]
        lo = max((qpos[x.exam_question_id] for x in confident if x.position < a.position), default=-1)
        hi = min((qpos[x.exam_question_id] for x in confident if x.position > a.position), default=10**9)
        if lo < qpos.get(a.exam_question_id, -2) < hi:
            a.status = "MAPPED"  # counts as a confident neighbour for the answers after it
            a.mapping_note = f"No readable number: mapped to Q{a.normalized_number} by content and answer order"


SUGGESTION_MARGIN = 0.15


def _spread_content_suggestions(answers: list, qs: list, suggested: list[tuple[Any, list[dict]]]) -> None:
    """Unlabelled answers suggested for the same question: the strongest content match keeps it; each other one
    moves to its next close candidate that is free and fits the answer order (between the questions confidently
    answered before and after it). Results stay NEEDS_REVIEW suggestions."""
    qpos = {q.id: q.position for q in qs}
    by_q: dict[str, list[tuple[Any, list[dict]]]] = {}
    for a, det in suggested:
        by_q.setdefault(a.exam_question_id, []).append((a, det))
    for qid, group in by_q.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: -(x[1][0].get("score") or 0))
        for a, det in group[1:]:
            confident = [x for x in answers if x.status == "MAPPED" and x.exam_question_id in qpos]
            lo = max((qpos[x.exam_question_id] for x in confident if x.position < a.position), default=-1)
            hi = min((qpos[x.exam_question_id] for x in confident if x.position > a.position), default=10**9)
            taken = {x.exam_question_id for x in answers if x.exam_question_id and x is not a and x.status != "IGNORED"}
            top = det[0].get("score") or 0
            for cand in sorted(det, key=lambda d: -(d.get("score") or 0)):
                cid = cand.get("id")
                if (cid and cid != qid and cid not in taken and (cand.get("score") or 0) >= top - SUGGESTION_MARGIN
                        and lo < qpos.get(cid, -2) < hi):
                    a.exam_question_id = cid
                    a.normalized_number = cand.get("num")
                    a.mapping_note = f"Suggested Q{cand.get('num')} from content and answer order (please confirm)"
                    break


def apply_key_mapping(db: Session, exam_id: str, doc_id: str) -> None:
    qs = exam_questions(db, exam_id)
    keys = db.query(AnswerKey).filter_by(exam_id=exam_id, document_id=doc_id).order_by(AnswerKey.created_at).all()
    prev_qid = None
    for idx, k in enumerate(keys, 1):
        res = map_label(
            k.raw_question_number,
            qs,
            k.ocr_confidence,
            get_settings().min_label_confidence,
            answer_text=k.answer_text,
            answer_position=idx,
            total_answers=len(keys),
            prev_question_id=prev_qid,
            check_content=False,  # a printed key label is authoritative; content checks are for handwritten labels
        )
        k.normalized_number, k.exam_question_id = res.normalized_number, res.question_id
        k.mapping_status, k.mapping_note, k.mapping_candidates = res.status, res.note, res.candidates
        if res.question_id:
            prev_qid = res.question_id
    db.flush()
    refresh_key_state(db, exam_id)


def refresh_key_state(db: Session, exam_id: str) -> None:
    """Recompute duplicate flags and mark mismatches for active keys (called after any key edit)."""
    qmap = {q.id: q for q in exam_questions(db, exam_id)}
    keys = db.query(AnswerKey).filter_by(exam_id=exam_id, is_active=True).all()
    dups = flag_duplicates(keys)
    for k in keys:
        if k.exam_question_id in dups:
            k.mapping_status, k.mapping_note = "NEEDS_REVIEW", DUP_NOTE
        elif k.mapping_status == "NEEDS_REVIEW" and (k.mapping_note or "").startswith("DUPLICATE_MAPPING"):
            k.mapping_status, k.mapping_note = "MAPPED", None
        q = qmap.get(k.exam_question_id) if k.exam_question_id else None
        if (getattr(q,"structure",None) or {}).get("root"):
            k.mark_mismatch = bool(q and k.marks != q.max_marks)
            continue  # Never silently repair printed CBSE allocations or rebuild its rubric.
        # Inherit question max_marks if answer key marks was missing
        if (k.marks is None or k.marks == 0.0) and q and q.max_marks is not None:
            k.marks = q.max_marks
        # Correct section total misattribution (e.g. 10 Marks from Section C header)
        elif k.marks is not None and q and q.max_marks is not None and k.marks > q.max_marks * 1.5:
            k.marks = q.max_marks
        k.mark_mismatch = bool(
            q and k.marks is not None and q.max_marks is not None and abs(k.marks - q.max_marks) > 1e-9
        )
        refresh_rubric(k, q)
    db.flush()


def refresh_rubric(key: AnswerKey, q: ExamQuestion | None) -> None:
    """Rebuild the key's marking rubric with the subject's formatter. A rubric that comes out different from the one
    the teacher confirmed needs confirming again; the same rubric keeps its confirmation."""
    if q is None or (getattr(q,"structure",None) or {}).get("root"):
        return
    built = formatter.current().build_rubric(q.question_text, key.answer_text, list(key.criteria or []), q.max_marks)
    new = built.to_dict() if built is not None else None
    if new != key.rubric:
        key.rubric, key.rubric_status = new, "UNREVIEWED"


def mapping_summary(db: Session, ev: Evaluation) -> dict:
    qs = exam_questions(db, ev.exam_id)
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    live = [a for a in answers if a.status != "IGNORED"]
    mapped_q = {a.exam_question_id for a in live if a.status not in ("UNMAPPED", "NEEDS_REVIEW") and a.exam_question_id}

    # Questions that have answers with suggested candidates
    suggested_q = set()
    for a in live:
        if a.status == "NEEDS_REVIEW" and a.mapping_candidates:
            for cid in a.mapping_candidates:
                if cid not in mapped_q:
                    suggested_q.add(cid)

    # Questions completely missing an answer
    missing = [q for q in qs if q.id not in {a.exam_question_id for a in live if a.exam_question_id}]

    return {
        "total_questions": len(qs),
        "mapped": len(mapped_q),
        "suggested": len(suggested_q),
        "needs_review": sum(a.status == "NEEDS_REVIEW" for a in live),
        "unmapped": sum(a.status == "UNMAPPED" for a in live),
        "missing": len(missing),
        "ignored": len(answers) - len(live),
        "missing_question_ids": [q.id for q in missing],
        "anomalies": [a for a in detect_mapping_anomalies(live,qs) if not (a["type"]=="DUPLICATE_ASSIGNMENT" and a.get("question_id") in {q.id for q in qs if getattr(q,"structure",None)})],
    }
