"""A second look at each page of a student's sheet: the first reading is checked against the image.

The first read of a page misreads in predictable ways: an option letter ("c)" read as "D)" or dropped), a
struck-out option copied, carbons lost from a drawn chain. Two more reads look for them: the whole page with the
first reading beside it, and two zoomed crops of the left side of the page, where the question numbers, option
letters and strike lines are twice the size.

None of the three reads is reliably better than the others (each misreads a letter now and then), so a later
read never overwrites the first one. Where they disagree the answer gets a low reading confidence and the
disagreement is kept with the page reading, so a teacher checks exactly those answers. Without token
probabilities the first read has no measured confidence of its own; this is it. The one repair: a reading that
starts with a lone "Q" takes the zoomed option letter (no option is called Q, it is a misread "c)").
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from . import prompts
from .schemas import StudentPageCheck, StudentPageResult

log = logging.getLogger("adem.ocr.check")

AGREED = 0.9      # the second look found the reading right
DIFFERS = 0.5     # a second read differs (its text is kept as a suggestion), or [unclear] is left in the reading
DOUBTFUL = 0.4    # unsure, option letters disagree, struck-out words may be in the reading, or a lone "Q"

# an objective answer starting with a lone "Q" ("Q II and IV"): no option is called Q
_LONE_Q = re.compile(r"^\s*Q(?![0-9A-Za-z])[\s,.)]*")
_OPTION = re.compile(r"^\s*\(?([a-dA-D])\s*[).]\s*")  # the option letter a student writes first: c)  (C)  d.
_ZOOM_WIDTH = 0.6  # question numbers and option letters are on the left of the line


def _ids(parsed: StudentPageResult) -> list[str]:
    """One id per answer, in order: the model's own when it gave unique ones, else ans_001, ans_002, ..."""
    ids = [a.answer_id for a in parsed.answers]
    if all(ids) and len(set(ids)) == len(ids):
        return ids
    return [f"ans_{i:03d}" for i in range(1, len(parsed.answers) + 1)]


def _alnum(t: str) -> str:
    return re.sub(r"[\W_]+", "", t).casefold()


def _same(a: str, b: str) -> bool:
    """Equal but for capital letters, spacing and punctuation (not misreadings)."""
    return _alnum(a) == _alnum(b)


def _norm_number(n: str | None) -> str:
    return re.sub(r"^q(?:uestion)?\.?\s*", "", (n or "").strip().casefold()).rstrip(").>:,. ")


def zoom_rows(source, out_dir, page_number: int, system: str, call) -> dict[str, dict]:
    """The start of each answer line and its struck-out words, read from two zoomed crops of the page's left side.
    {question number: {"start", "struck"}}; a number the two crops read with different letters is left out."""
    from PIL import Image
    from .schemas import PageLineStarts
    im = Image.open(source)
    w, h = im.size
    rows: dict[str, dict] = {}
    clash: set[str] = set()
    for k, (top, bottom) in enumerate([(0, h // 2 + h // 25), (h // 2 - h // 25, h)]):
        crop = Path(out_dir) / f"page-{page_number:03d}-zoom{k + 1}.png"
        im.crop((0, top, int(w * _ZOOM_WIDTH), bottom)).save(crop)
        for row in call(system, prompts.student_line_start_prompt(), PageLineStarts, crop).parsed.rows:
            num = _norm_number(row.question_number)
            if not num or not row.start.strip():
                continue
            seen = rows.get(num)
            a, b = (_OPTION.match(seen["start"]) if seen else None), _OPTION.match(row.start)
            if a and b and a[1].casefold() != b[1].casefold():
                clash.add(num)  # the overlap read twice with different letters: no evidence either way
            rows.setdefault(num, {"start": row.start, "struck": []})["struck"] += row.struck
    return {n: r for n, r in rows.items() if n not in clash}


def compare_zoom(text: str, start: str, struck: list[str]) -> tuple[str, list[str]]:
    """The reading against the zoomed line start: (the reading, with a lone "Q" replaced by the zoomed option
    letter; the doubts). Everything else is left as read."""
    doubts = [f"may include struck-out words: {p.strip()}" for p in struck
              if p.strip() and p.strip().casefold() in text.casefold()]
    zoom = _OPTION.match(start)
    if not zoom:
        return text, doubts
    letter = zoom[0].strip()
    lone_q = _LONE_Q.match(text)
    if lone_q:
        return f"{letter} {text[lone_q.end():]}", doubts + [f"option letter read as Q; zoomed read: {letter}"]
    mine = _OPTION.match(text)
    if mine and mine[1].casefold() != zoom[1].casefold():
        doubts.append(f"option letter: reading {mine[0].strip()}, zoomed read {letter}")
    elif not mine and _alnum(start[zoom.end():])[:3] == _alnum(text)[:3] != "":
        doubts.append(f"option letter missing from the reading; zoomed read: {letter}")
    return text, doubts


def check_page(parsed: StudentPageResult, page_number: int, image, system: str, call, measured: bool,
               zoom_source=None, zoom_dir=None) -> dict:
    """Check the page's answers against the image with `call` (chat_structured) and set their ocr_confidence;
    with `zoom_source` (the full-size page) also against zoomed crops of it (saved in `zoom_dir`). Returns the
    record kept next to the page reading: the second reads and each answer's doubts."""
    if not parsed.answers:
        return {}
    ids = _ids(parsed)
    listing = [{"answer_id": i, "question_number": a.question_number, "answer_text": a.answer_text}
               for i, a in zip(ids, parsed.answers)]
    result = call(system, prompts.student_answer_check_prompt(page_number, listing), StudentPageCheck, image)
    verdicts = {c.answer_id: c for c in result.parsed.checks if c.answer_id}
    zoomed = zoom_rows(zoom_source, zoom_dir, page_number, system, call) if zoom_source and zoom_dir else {}
    record = {"raw": result.raw, "zoom": zoomed, "applied": []}
    started = set()
    for answer_id, answer in zip(ids, parsed.answers):
        check = verdicts.get(answer_id)
        doubts = list(check.doubts) if check else ["not checked"]
        conf = AGREED if check and check.status == "OK" else DOUBTFUL
        suggestion = None
        if check and check.status == "CORRECTED":
            if _same(answer.answer_text, check.answer_text) or not check.answer_text.strip():
                conf = AGREED  # only case or punctuation differed: the reading stands
            else:
                conf, suggestion = DIFFERS, check.answer_text.strip()
                doubts += check.changes or ["second reading differs"]
        num = _norm_number(answer.question_number)
        if num in zoomed and num not in started:  # a zoomed line start is the start of the question's first answer
            text, more = compare_zoom(answer.answer_text, zoomed[num]["start"], zoomed[num]["struck"])
            answer.answer_text, doubts = text, doubts + more
            if more:
                conf = min(conf, DOUBTFUL)
        started.add(num)
        if _LONE_Q.match(answer.answer_text):
            conf = DOUBTFUL
            doubts.append("option letter read as Q (usually a misread c)")
        if "[unclear]" in answer.answer_text.lower():
            conf = min(conf, DIFFERS)
        # a measured (token-probability) confidence is kept when it is the lower of the two
        answer.ocr_confidence = min(answer.ocr_confidence, conf) if measured and answer.ocr_confidence is not None else conf
        record["applied"].append({"answer_id": answer_id, "question_number": answer.question_number,
                                  "confidence": conf, "doubts": doubts, "second_reading": suggestion})
    doubtful = [f"{a['question_number']}" for a in record["applied"] if a["confidence"] < AGREED]
    if doubtful:
        log.info("Page %s: readings to check: %s", page_number, ", ".join(doubtful))
    return record
