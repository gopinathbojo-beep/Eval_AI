"""Join a student's answers across pages and match them to the questions with one text-only AI call.

Pages are read one at a time, so an answer running onto the next page arrives as a piece with no number at the top of
that page, and a page can hold the end of one answer and the start of the next. Here the AI sees every piece of every
page in reading order, with the number the student wrote on each, and says which pieces make up the answer to each
question (cutting a piece where a new answer starts inside it) and which pieces are no answer at all.

The reply is checked strictly; when the call fails or the reply does not hold together, None is returned and the
sheet falls back to the rule segmenter (formatter/common/answers.py) and the rule mapper (mapping_service.py)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ..cbse.extraction import BRANCHES, BRANCH_TITLES, has_branches, option_text
from ..config import get_settings
from ..formatter.common.answers import SegmentedAnswer, _merge_bboxes, _strip_sheet_furniture
from ..formatter.common.numbering import normalize_question_number, parent_number
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured

log = logging.getLogger("adem.joiner")

_PART_START = re.compile(r"^\s*\(?\s*(?:[a-hA-H]|[ivxIVX]{1,4}|\d{1,2})\s*[).:]")
MAX_UNPLACED_SHARE = 0.3   # a reply that leaves more of the sheet unplaced than this is not trusted
PROMPT_TEXT_LIMIT = 1500   # characters of one piece shown to the AI (the full text is kept for the answer)


# ---------------------------------------------------------------- reply schema
class JoinPart(BaseModel):
    model_config = {"extra": "ignore"}
    block: str
    start: str | None = None   # the first words of this answer inside the piece, when the piece holds two answers


class JoinAnswer(BaseModel):
    model_config = {"extra": "ignore"}
    question: str | None = None
    parts: list[JoinPart] = Field(default_factory=list)

    @field_validator("question", mode="before")
    @classmethod
    def _q(cls, v):
        return None if v is None or str(v).strip().lower() in ("", "null", "none", "-") else str(v)

    @field_validator("parts", mode="before")
    @classmethod
    def _parts(cls, v):  # ["p1.b2", ...] is read as [{"block": "p1.b2"}, ...]
        return [{"block": p} if isinstance(p, str) else p for p in (v or [])]


class JoinResult(BaseModel):
    model_config = {"extra": "ignore"}
    answers: list[JoinAnswer] = Field(default_factory=list)
    ignored: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _shape(cls, v):
        if isinstance(v, list):   # the answers alone, without the wrapping object
            return {"answers": v}
        if isinstance(v, dict) and "answers" not in v:   # the answers under another name ("groups", "items", ..)
            lists = [x for k, x in v.items() if isinstance(x, list) and k != "ignored"]
            if len(lists) == 1:
                return {**v, "answers": lists[0]}
        return v

    @field_validator("ignored", mode="before")
    @classmethod
    def _ignored(cls, v):
        return [str(x.get("block") if isinstance(x, dict) else x) for x in (v or [])]


class JoinRejected(ValueError):
    """The reply does not hold together; the rules take the sheet."""


# ---------------------------------------------------------------- pieces of the sheet
@dataclass
class Block:
    id: str
    index: int
    page: int
    label: str | None
    text: str
    bbox: dict | None
    conf: float | None


@dataclass
class Joined:
    """One answer the AI put together: the segmented answer and the question it answers (None: not matched)."""
    answer: SegmentedAnswer
    question: Any | None
    ignored: bool = False
    blocks: list[str] = field(default_factory=list)


def blocks_from_pages(page_results: list[tuple[dict, Any]]) -> list[Block]:
    out: list[Block] = []
    for page_info, res in page_results:
        page = page_info["page_number"]
        for n, a in enumerate(getattr(res, "answers", None) or [], 1):
            text = (a.answer_text or "").strip()
            for cb in getattr(a, "content_blocks", None) or []:
                t = (cb.get("text") or cb.get("raw_text") or "").strip() if isinstance(cb, dict) else ""
                if t and t not in text:
                    text = f"{text}\n{t}".strip()
            text = _strip_sheet_furniture(text)
            label = (a.question_number or a.raw_question_label or "").strip() or None
            if not text and not label:
                continue
            bbox = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            out.append(Block(f"p{page}.b{n}", len(out), page, label, text, bbox, a.ocr_confidence))
    return out


# ---------------------------------------------------------------- prompt
SYSTEM = ("You organise a student's handwritten exam answer sheet. The sheet was read page by page into pieces; you "
          "decide which pieces form the answer to each question. Reply with JSON only.")


def _question_lines(questions: list[Any]) -> str:
    lines = []
    for q in questions:
        tree = (getattr(q, "structure", None) or {}).get("tree")
        if has_branches(tree):  # both options under one number: a student's answer may follow either
            text = " OR ".join(f"{BRANCH_TITLES[b]}: " + re.sub(r"\s+", " ", option_text(q.question_text, b))[:120]
                               for b in BRANCHES)
        else:
            text = re.sub(r"\s+", " ", q.question_text or "")[:160]
        marks = f" [{q.max_marks:g} marks]" if q.max_marks is not None else ""
        lines.append(f"Q{q.display_number}{marks}: {text}")
    return "\n".join(lines)


def build_prompt(blocks: list[Block], questions: list[Any]) -> str:
    pieces = "\n\n".join(
        f"[{b.id}] page {b.page}, number written: {b.label or '-'}\n{b.text[:PROMPT_TEXT_LIMIT]}" for b in blocks)
    return (
        "QUESTIONS OF THE PAPER\n" + _question_lines(questions) +
        "\n\nPIECES OF THE STUDENT'S SHEET, IN READING ORDER\n" + pieces +
        "\n\nGroup the pieces into the student's answers:\n"
        "- The number the student wrote is the strongest evidence of the question. Trust the content over it only "
        "when the content plainly answers a different question (the number was misread or miswritten).\n"
        "- A piece with no number, at the top of a page or between numbered pieces, usually continues the answer "
        "before it (an answer running onto the next page). Start a new answer only when its content clearly answers "
        "another question.\n"
        "- An answer whose last sentence is unfinished (\"... only when an\") continues in the piece that completes "
        "it, even when that piece starts with a part marker such as (ii) and even when it is on another page.\n"
        "- A sub-part (i), (ii), a) written after a numbered answer belongs to a question that has such parts; use "
        "\"question\": null only when the piece answers none of the listed questions.\n"
        "- Steps numbered 1), 2), (i), (ii), a), b) inside an answer are part of that answer unless the paper has "
        "those as separate questions.\n"
        "- One piece can hold the end of one answer and the start of the next: list it in both answers and give, "
        "for the later answer, \"start\": the first few words of that answer exactly as they appear in the piece.\n"
        "- Every piece goes in exactly one answer, or in \"ignored\" when it answers no question (rough work, the "
        "student details box, a heading, crossed-out text).\n"
        "- Use the question numbers exactly as listed (\"Q\" not needed). An answer to a question not on the list "
        "gets \"question\": null.\n"
        "- List the answers in the order they appear on the sheet; one entry per question.\n\n"
        'Reply: {"answers": [{"question": "7", "parts": [{"block": "p3.b2"}, {"block": "p4.b1"}]}, '
        '{"question": "8", "parts": [{"block": "p4.b1", "start": "Given that"}]}], "ignored": ["p1.b1"]}')


# ---------------------------------------------------------------- reading the reply
def _question_for(number: str | None, by_norm: dict[str, Any]) -> Any | None:
    if not number:
        return None
    norm = normalize_question_number(re.sub(r"^\s*Q\.?\s*", "", number, flags=re.I)) or number.strip()
    if norm in by_norm:
        return by_norm[norm]
    root = parent_number(norm)
    return by_norm.get(root) if root else None   # "26(iii)" on a paper scored by whole question 26


def _find(text: str, start: str) -> int:
    """Where the quoted words begin in the piece (whitespace and case forgiven), or -1."""
    i = text.find(start)
    if i >= 0:
        return i
    words = start.split()
    if not words:
        return -1
    m = re.search(r"\s+".join(re.escape(w) for w in words), text, re.I)
    return m.start() if m else -1


def assemble(reply: JoinResult, blocks: list[Block], questions: list[Any]) -> list[Joined]:
    by_id = {b.id: b for b in blocks}
    by_norm = {q.normalized_number: q for q in questions if q.normalized_number}

    # 1. one entry per question (the AI may list a question twice: the pieces are joined in sheet order)
    entries: list[tuple[str | None, list[JoinPart]]] = []
    seen_q: dict[str, int] = {}
    for a in reply.answers:
        q = _question_for(a.question, by_norm)
        key = q.id if q is not None else None
        if key is not None and key in seen_q:
            entries[seen_q[key]][1].extend(a.parts)
            continue
        if key is not None:
            seen_q[key] = len(entries)
        entries.append((a.question, list(a.parts)))

    # 2. where each answer starts inside each piece
    cuts: dict[str, list[tuple[int, int]]] = {}       # block id -> [(offset, entry index)]
    for e, (_, parts) in enumerate(entries):
        for p in parts:
            if p.block not in by_id:
                raise JoinRejected(f"unknown piece {p.block}")
            b = by_id[p.block]
            offset = 0
            if p.start and p.start.strip():
                offset = _find(b.text, p.start.strip())
                if offset < 0:
                    offset = 0 if not cuts.get(p.block) else -1
                if offset < 0:
                    raise JoinRejected(f"start words of {p.block} not found")
            clash = next((k for k, (o, other) in enumerate(cuts.get(p.block, [])) if o == offset and other != e), None)
            if clash is not None:
                # one piece in two answers with no place to cut it: the number written on it decides, else the first
                written = _question_for(b.label, by_norm) if b.label else None
                mine = _question_for(entries[e][0], by_norm)
                if written is not None and mine is not None and written.id == mine.id:
                    cuts[p.block][clash] = (offset, e)
                log.info("Piece %s was given to two answers; kept with Q%s", p.block, entries[cuts[p.block][clash][1]][0])
                continue
            if not any(other == e for _, other in cuts.get(p.block, [])):
                cuts.setdefault(p.block, []).append((offset, e))
    ignored = {i for i in reply.ignored if i in by_id and i not in cuts}
    # set aside only what looks like no answer: a piece with a written number or opening like a sub-part ("i) ..")
    # is answer text, and losing it costs the student marks; it goes to the rules instead (unmatched below)
    doubtful = {i for i in ignored if by_id[i].label or _PART_START.match(by_id[i].text)}
    ignored -= doubtful

    # 3. pieces the reply left out continue the answer before them (or after, at the very start)
    unplaced = [b for b in blocks if b.id not in cuts and b.id not in ignored and b.id not in doubtful]
    if blocks and len(unplaced) > MAX_UNPLACED_SHARE * len(blocks):
        raise JoinRejected(f"{len(unplaced)} of {len(blocks)} pieces not placed")
    for b in unplaced:
        before = next((blocks[i] for i in range(b.index - 1, -1, -1) if blocks[i].id in cuts), None)
        after = next((blocks[i] for i in range(b.index + 1, len(blocks)) if blocks[i].id in cuts), None)
        neighbour = before or after
        if neighbour is None:
            raise JoinRejected("no answer to attach the unplaced pieces to")
        owner = max(cuts[neighbour.id])[1] if neighbour is before else min(cuts[neighbour.id])[1]
        cuts[b.id] = [(0, owner)]

    # 4. the text of each answer, piece by piece in sheet order
    segs: dict[int, list[tuple[int, int, Block, str]]] = {}
    for bid, points in cuts.items():
        b = by_id[bid]
        points = sorted(points)
        if points[0][0] > 0:   # text before the first cut belongs to the first answer listed in the piece
            points[0] = (0, points[0][1])
        for k, (offset, e) in enumerate(points):
            end = points[k + 1][0] if k + 1 < len(points) else len(b.text)
            text = b.text[offset:end].strip()
            segs.setdefault(e, []).append((b.index, offset, b, text))

    out: list[Joined] = []
    for e, pieces in segs.items():
        pieces.sort(key=lambda p: (p[0], p[1]))
        first = pieces[0][2]
        text = "\n".join(t for *_, t in pieces if t).strip()
        if not text:
            continue
        number, _ = entries[e]
        q = _question_for(number, by_norm)
        bbox = None
        for _, _, b, _ in pieces:
            if b.page == first.page:
                bbox = _merge_bboxes(bbox, b.bbox) if bbox else b.bbox
        confs = [b.conf for _, _, b, _ in pieces if b.conf is not None]
        written = first.label if pieces[0][1] == 0 else None
        seg = SegmentedAnswer(
            raw_question_number=written or (q.display_number if q is not None else number),
            normalized_number=q.normalized_number if q is not None else normalize_question_number(number or ""),
            answer_text=text, raw_ocr_text=text, page_number=first.page, bbox=bbox,
            ocr_confidence=sum(confs) / len(confs) if confs else None)
        out.append(Joined(seg, q, blocks=[b.id for _, _, b, _ in pieces]))
    for bid in ignored | doubtful:
        b = by_id[bid]
        seg = SegmentedAnswer(raw_question_number=b.label, normalized_number=None, answer_text=b.text,
                              raw_ocr_text=b.text, page_number=b.page, bbox=b.bbox, ocr_confidence=b.conf)
        out.append(Joined(seg, None, ignored=bid in ignored, blocks=[bid]))

    order = {b.id: b.index for b in blocks}
    out.sort(key=lambda j: min(order[i] for i in j.blocks))
    for n, j in enumerate(out, 1):
        j.answer.position = n
    if not any(j.question is not None for j in out):
        raise JoinRejected("no answer matched to a question")
    return out


def join(page_results: list[tuple[dict, Any]], questions: list[Any], ask=None) -> list[Joined] | None:
    """The sheet's answers joined and matched by the AI, or None for the rules to take the sheet."""
    s = get_settings()
    if not s.ai_join_answers or not questions:
        return None
    blocks = blocks_from_pages(page_results)
    if not blocks:
        return None
    prompt = build_prompt(blocks, questions)
    try:
        if ask is None:
            reply = chat_structured(SYSTEM, prompt, JoinResult, model=s.medium_model).parsed
        else:
            reply = ask(SYSTEM, prompt)
        joined = assemble(reply, blocks, questions)
    except (AIResponseError, AIUnavailable, JoinRejected) as e:
        log.warning("AI joining not used; the rules take the sheet: %s", getattr(e, "detail", None) or e)
        return None
    except Exception:  # never let the joiner stop a sheet: the rules still work
        log.exception("AI joining failed; the rules take the sheet")
        return None
    log.info("AI joined %d pieces into %d answers (%d not answers)", len(blocks),
             sum(1 for j in joined if not j.ignored), sum(1 for j in joined if j.ignored))
    return joined
