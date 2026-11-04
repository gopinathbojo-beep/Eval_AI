"""Writes a question paper and its answer key from retrieved textbook passages (retrieval-augmented generation).

For each section of the blueprint: retrieve passages from the chosen chapters, add board sample-paper questions of
the same marks as style examples, and ask the AI for that section's questions with answers and marking points,
each citing the passage ids it used. Citations to passages that were not supplied are dropped, and every answer is
checked word-by-word against the passages it cites (reference/search.coverage): weakly supported answers are
flagged for the teacher. Nothing is final until a teacher reviews it."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import GeneratedPaper
from ..ocr import remote
from ..reference.search import coverage, query_terms
from .blueprint import Blueprint, Slot
from .retrieve import Passage, Pool, style_examples

log = logging.getLogger("adem.generation")
BATCH = 8  # questions per AI call: keeps each reply well inside AI_MAX_OUTPUT_TOKENS
GROUNDED_AT, PARTIAL_AT = 0.5, 0.3
STALE_AFTER = timedelta(minutes=30)
_NUMERIC = ("mathematics", "physics", "chemistry", "accountancy", "economics", "computer", "informatics")

SYSTEM = """You are an experienced CBSE paper setter writing a board-style question paper and its marking scheme.
Rules:
- Write every question ONLY from the numbered TEXTBOOK PASSAGES given. Do not use facts that are not in them.
- Cite in "source_ids" the passage ids each question and answer was taken from (at least one).
- Match the requested marks and question type exactly. Use CBSE wording ("Give reasons", "Justify", "Assertion (A)...").
- For an MCQ put the four options in "options" (text only, no letters) and the correct option letter and text in "answer".
- "answer" is the model answer a student should write; "marking_points" split the marks (each point with marks;
  the points add up to the question's marks).
- When "with_choice" is true, also write an alternative question of the same marks in "or" (same fields).
- Vary difficulty: about 20% easy recall, 50% understanding/application, 30% higher-order thinking.
- Do not repeat or closely paraphrase any question listed under ALREADY ASKED.
- Questions must stand alone: never refer to the book ("Activity 6", "Example 3", "Fig. 2.1", "the passage above",
  "as given in the textbook"); state the needed data in the question itself.
- Write in the medium of the passages (English, Hindi or Tamil). Use plain text; write maths as a student would
  type it (x^2, sqrt(3), 1/2, π, θ).
Return ONLY JSON: {"questions": [{"number": 1, "type": "...", "text": "...", "options": [], "answer": "...",
"marking_points": [{"point": "...", "marks": 1}], "source_ids": [12], "difficulty": "easy|medium|hard",
"or": null}]}"""


def _parse(raw: str) -> dict:
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", raw.strip(), flags=re.I).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise


def _prompt(subject: str, standard: int, slots: list[Slot], passages: list[Passage], examples: list[str],
            asked: list[str], difficulty: str, notes: str) -> str:
    lines = [f"CLASS {standard}, SUBJECT: {subject}. Overall difficulty: {difficulty}."]
    if notes.strip():
        lines.append(f"TEACHER'S INSTRUCTIONS: {notes.strip()[:800]}")
    lines.append("\nWRITE THESE QUESTIONS:")
    for s in slots:
        lines.append(f"- number {s.number}: section {s.section}, {s.marks:g} mark(s), type: {s.kind}, with_choice: "
                     f"{str(s.with_choice).lower()}")
    if examples:
        lines.append("\nSTYLE EXAMPLES (real CBSE sample-paper questions of these marks with their marking scheme; "
                     "copy the style, NOT the content):")
        lines += [f"---\n{e}" for e in examples]
    lines.append("\nTEXTBOOK PASSAGES:")
    for p in passages:
        lines.append(f"[{p.id}] ({p.chapter}, p.{p.pages})\n{p.text}")
    if asked:
        lines.append("\nALREADY ASKED:\n" + "\n".join(f"- {q[:160]}" for q in asked[-60:]))
    return "\n".join(lines)


def fit_points(points: list[dict], marks: float, answer: str, mcq: bool) -> list[dict]:
    """Marking points that add up exactly to the question's marks: an MCQ is one point; otherwise the AI's split is
    kept when it adds up, rescaled to half marks when it does not, and one whole-answer point when there is none."""
    points = [p for p in points if p["point"] and p["marks"] > 0]
    if mcq or not points:
        return [{"point": answer or "Correct answer", "marks": marks}]
    total = sum(p["marks"] for p in points)
    if abs(total - marks) < 1e-9:
        return points
    scaled = [{"point": p["point"], "marks": max(0.5, round(p["marks"] * marks / total * 2) / 2)} for p in points]
    while sum(p["marks"] for p in scaled) > marks and len(scaled) > 1:  # rounding overshoot: trim the largest
        big = max(scaled, key=lambda p: p["marks"])
        if big["marks"] <= 0.5:
            scaled.remove(big)
        else:
            big["marks"] -= 0.5
    scaled[-1]["marks"] += marks - sum(p["marks"] for p in scaled)
    if scaled[-1]["marks"] <= 0:
        return [{"point": answer or "Correct answer", "marks": marks}]
    return scaled


def _clean_item(raw: dict, slot: Slot, passages: dict[int, Passage], numeric: bool) -> dict:
    def ids(x):
        out = []
        for v in x.get("source_ids") or []:
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
            if v in passages and v not in out:
                out.append(v)
        return out

    def one(x: dict) -> dict:
        points = [{"point": str(p.get("point") or "").strip(), "marks": float(p.get("marks") or 0)}
                  for p in (x.get("marking_points") or []) if isinstance(p, dict) and p.get("point")]
        src = ids(x)
        answer = str(x.get("answer") or "").strip()
        support = None
        if src and answer:
            terms = query_terms(answer + " " + " ".join(p["point"] for p in points))
            support = round(coverage(terms, " ".join(passages[i].text for i in src)), 2) if terms else None
        options = [str(o).strip() for o in (x.get("options") or []) if str(o).strip()][:6]
        points = fit_points(points, slot.marks, answer, bool(options) and slot.marks <= 1)
        notes = []
        if not src:
            notes.append("No textbook passage cited: check this question against the book.")
        elif support is not None and support < PARTIAL_AT and not numeric:
            notes.append("The answer is weakly supported by the cited passages: check it.")
        status = ("UNSUPPORTED" if not src else "GROUNDED" if support is None or support >= GROUNDED_AT or numeric
                  else "PARTIAL" if support >= PARTIAL_AT else "WEAK")
        return {"type": str(x.get("type") or slot.kind)[:120], "text": str(x.get("text") or "").strip(),
                "options": options,
                "answer": answer, "marking_points": points, "difficulty": str(x.get("difficulty") or "medium"),
                "sources": [{"id": i, "chapter": passages[i].chapter, "title": passages[i].title,
                             "pages": passages[i].pages, "excerpt": passages[i].text[:400]} for i in src],
                "support": support, "grounding": status, "notes": notes}

    item = {"number": slot.number, "section": slot.section, "marks": slot.marks, **one(raw)}
    alt = raw.get("or")
    item["or"] = one(alt) if slot.with_choice and isinstance(alt, dict) and alt.get("text") else None
    return item


def _complete(item: dict, slot: Slot) -> bool:
    """Everything a question needs to go straight into an exam: text, an answer, and its OR when one was asked for."""
    parts = [item] + ([item["or"]] if item["or"] else [])
    return (all(p["text"] and p["answer"] for p in parts) and (item["or"] is not None or not slot.with_choice))


def _section(subject_name: str, standard: int, subject: str, slots: list[Slot], pool: Pool, db: Session,
             asked: list[str], difficulty: str, notes: str, seed: int | None) -> list[dict]:
    per = 2 if slots[0].marks <= 2 else 3
    passages = pool.take(min(max(len(slots) * per, 6), 24))
    if not passages:
        raise RuntimeError("No textbook passages are loaded for the chosen chapters.")
    by_id = {p.id: p for p in passages}
    examples = style_examples(db, standard, subject, slots[0].marks, seed=seed)
    prompt = _prompt(subject_name, standard, slots, passages, examples, asked, difficulty, notes)
    numeric = any(w in subject for w in _NUMERIC)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw, _ = remote.call(SYSTEM, prompt, None, structured=True)
            got = _parse(raw).get("questions") or []
            by_num = {}
            for g in got:
                try:
                    by_num.setdefault(int(g.get("number")), g)
                except (TypeError, ValueError):
                    continue
            # numbers the AI skipped or renumbered: fill in order from the unmatched answers
            spare = [g for g in got if g not in by_num.values()]
            out = []
            for s in slots:
                g = by_num.get(s.number) or (spare.pop(0) if spare else None)
                if g is None:
                    raise ValueError(f"question {s.number} missing from the AI reply")
                out.append(_clean_item(g, s, by_id, numeric))
            bad = [s.number for s, q in zip(slots, out) if not _complete(q, s)]
            if bad and attempt == 0:
                raise ValueError(f"questions {bad} came back without text, answer or OR alternative")
            for s, q in zip(slots, out):  # second try still incomplete: drop a missing OR rather than ship a gap
                if s.with_choice and q["or"] is None:
                    s.with_choice = False
                if not q["answer"] or not q["text"]:
                    raise ValueError(f"question {s.number} has no text or answer")
            return out
        except remote.CompletionLimitError as e:
            last_error = e
            if len(slots) > 1:  # the reply was too long: write the section in two halves
                half = len(slots) // 2
                return (_section(subject_name, standard, subject, slots[:half], pool, db, asked, difficulty, notes, seed)
                        + _section(subject_name, standard, subject, slots[half:], pool, db,
                                   asked, difficulty, notes, seed))
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            log.warning("Generation reply rejected (attempt %d): %s", attempt + 1, e)
    raise RuntimeError(f"The AI did not return usable questions: {last_error}")


def generate(db: Session, bp: Blueprint, standard: int, subject: str, subject_name: str, source_ids: list[str],
             difficulty: str = "balanced", topics: str = "", notes: str = "", seed: int | None = None,
             progress=lambda msg: None) -> dict:
    pool = Pool(db, standard, subject, source_ids, topics, seed)
    if not pool.size:
        raise RuntimeError("No textbook passages are loaded for this class and subject. Load the reference library "
                           "(scripts/ingest_reference.py) first.")
    questions: list[dict] = []
    asked: list[str] = []
    batches = [(sec["key"], sec["slots"][i:i + BATCH]) for sec in bp.sections for i in range(0, len(sec["slots"]), BATCH)]
    for n, (key, slots) in enumerate(batches, 1):
        progress(f"Writing section {key} ({n} of {len(batches)})")
        items = _section(subject_name, standard, subject, slots, pool, db, asked, difficulty, notes, seed)
        questions += items
        asked += [q["text"] for q in items] + [q["or"]["text"] for q in items if q["or"]]
    flagged = sum(1 for q in questions if q["notes"] or (q["or"] and q["or"]["notes"]))
    return {**bp.as_dict(), "standard": standard, "subject": subject, "subject_name": subject_name,
            "questions": questions, "flagged": flagged,
            "chapters": sorted({s["chapter"] for q in questions for s in q["sources"]}),
            "generated_at": datetime.now(timezone.utc).isoformat()}


# ---------- background job ----------
def run_job(paper_id: str) -> None:
    from .blueprint import DEFAULT_MIX, LANGUAGE, board, custom
    with SessionLocal() as db:
        gp = db.get(GeneratedPaper, paper_id)
        if gp is None or gp.status not in ("QUEUED",):
            return
        gp.status, gp.stage = "GENERATING", "Retrieving textbook passages"
        db.commit()

        def progress(msg: str):
            gp.stage = msg[:200]
            db.commit()

        r = gp.request or {}
        try:
            name = r.get("subject_name") or gp.subject
            bp = board(r["profile_id"], name, gp.standard, r.get("choices", True)) if r.get("pattern") == "board" and r.get("profile_id") else None
            if bp is None:
                language = any(w in gp.subject for w in LANGUAGE)
                bp = custom(r.get("mix") or DEFAULT_MIX, name, gp.standard, int(r.get("duration_minutes") or 180), language, r.get("choices", True))
            if r.get("title"):
                bp.title = str(r["title"])[:300]
            paper = generate(db, bp, gp.standard, gp.subject, name, r.get("source_ids") or [],
                             r.get("difficulty") or "balanced", r.get("topics") or "", r.get("notes") or "",
                             r.get("seed"), progress)
            gp.paper, gp.title, gp.status, gp.stage, gp.error = paper, bp.title, "READY", None, None
            db.commit()
            if gp.exam_id:
                from .attach import attach_to_exam
                attach_to_exam(db, gp)
        except Exception as e:  # the job reports every failure to the teacher; nothing else is left half-done
            log.exception("Paper generation failed")
            db.rollback()
            gp = db.get(GeneratedPaper, paper_id)
            gp.status, gp.stage, gp.error = "FAILED", None, str(e)[:1000]
            db.commit()


def expire_stale(db: Session, gp: GeneratedPaper) -> None:
    """A job cut off by a server restart would otherwise show 'generating' forever."""
    updated = gp.updated_at if gp.updated_at.tzinfo else gp.updated_at.replace(tzinfo=timezone.utc)
    if gp.status in ("QUEUED", "GENERATING") and datetime.now(timezone.utc) - updated > STALE_AFTER:
        gp.status, gp.error = "FAILED", "Generation was interrupted (the server restarted). Generate again."
        db.commit()
