"""Tamil answer sheets segmented by alignment, and their self-repair before anything is flagged. Tamil subjects only.

answers.segment trusts the question numbers alone: a number the paper has, moving forward, starts the next answer, so
a heading IndicOCR lost or misread merges two answers or splits one. Here every line of the sheet is given to a
question in paper order, the assignment with the best total score over four kinds of evidence:
  numbers   a வினா heading or block label naming the question (strong); naming another question (weakly against)
  titles    a heading that copies the question's title ("படித்துப் புரிந்து விடையளித்தல்")
  key       the line's content words shared with that question's key
  order     answers follow the paper: going back is not possible and each question skipped costs a little
An answer starting with no number at all must be paid for by its key evidence.

Every boundary gets a confidence from its next-best alignment: how much better the chosen first line is than the best
other line for that question to start on. Self-repair, in order:
  1. next-best alignment: each doubtful boundary is moved to its next-best line, kept when more answers then match
     their own key (segment);
  2. re-reading: an answer that still resembles another question's key more than its own has its region read again
     by IndicOCR and the sheet segmented again, kept when more answers match their own key (reread_failing).
It replaces answers.segment only when USE_ALIGNMENT (__init__.py) is switched on, after the replay harness
(scripts/accuracy_report.py --segmenter both) shows it doing better on the stored sheets.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable

from . import format as tamil_format
from .answers import _part_marker, _same_title, add_text, blocks, continue_piece, emit
from ...numbering import normalize_question_number, parent_number, subpart_path

log = logging.getLogger("adem.tamil.align")

W_NUMBER = 3.0      # a line opening with the question's own number starts it
W_HEADING = 1.0     # ... more so when that number is a வினா heading
W_TITLE = 1.5       # a first line copying the question's title
W_KEY = 3.0         # a line wholly made of the question's key words (scaled by the share it has)
W_OTHER = 1.0       # starting on a line that names another question
W_NO_NUMBER = 2.5   # starting on a line that names no question
W_MID_BLOCK = 0.5   # ... and inside an IndicOCR block rather than at its start
W_SKIP = 0.5        # each question skipped between two answers
W_IGNORED = 1.5     # a number of a later question that starts nothing (twice that for a வினா heading)
LINE_TOKENS = 3     # a line needs this many content words for key evidence
LOW_CONFIDENCE = 0.5
KEY_MARGIN = 0.05   # an answer matches its own key when that key trails the best key by no more than this
MIN_TOKENS = 4      # answers shorter than this are not judged against the key
MAX_REREADS = 3     # regions read again per sheet
NEG = float("-inf")


@dataclass
class _Line:
    text: str
    page: int
    bbox: dict | None
    conf: float | None
    first: bool                 # the first line of an IndicOCR block piece
    label: str | None = None    # the piece's label (first line only)
    norm: str | None = None
    top: int | None = None      # the question number the label names
    heading: bool = False       # opened by a வினா heading
    tokens: frozenset = frozenset()


def _lines(page_results: list[tuple[dict, Any]]) -> list[_Line]:
    out = []
    for page, bbox, conf, label, piece, from_heading in blocks(page_results):
        norm = normalize_question_number(label) if label else None
        top = int(parent_number(norm)) if norm and parent_number(norm).isdigit() else None
        rows = [r for r in piece.splitlines() if r.strip()] or [""]
        for i, row in enumerate(rows):
            first = i == 0
            out.append(_Line(row, page, bbox, conf, first, label if first else None, norm if first else None,
                             top if first else None, from_heading and first,
                             frozenset(tamil_format.indic_tokens(row))))
    return out


def _similarity(tokens: set | frozenset, key: set) -> float:
    return len(tokens & key) / len(tokens) if tokens else 0.0


class _Scores:
    """Per line and question: the evidence that the line belongs to it (emit), starts it (start), or goes on in it
    (stay); question -1 is the sheet's title lines before the first answer."""

    def __init__(self, lines: list[_Line], numbers: list[int], titles: dict[int, str], keys: dict[int, set]):
        self.lines, self.numbers = lines, numbers
        self.index = {n: j for j, n in enumerate(numbers)}
        self.titles, self.keys = titles, keys

    def emit(self, u: int, j: int) -> float:
        line = self.lines[u]
        if j < 0 or len(line.tokens) < LINE_TOKENS or self.numbers[j] not in self.keys:
            return 0.0
        return W_KEY * _similarity(line.tokens, self.keys[self.numbers[j]])

    def start(self, u: int, j: int) -> float:
        line, n = self.lines[u], self.numbers[j]
        if line.top == n:
            s = W_NUMBER + (W_HEADING if line.heading else 0.0)
        else:
            s = -W_OTHER if line.top is not None else -W_NO_NUMBER - (0.0 if line.first else W_MID_BLOCK)
        if line.first and _same_title(line.text, self.titles.get(n)):
            s += W_TITLE
        return s

    def stay(self, u: int, j: int) -> float:
        line = self.lines[u]
        if line.top is not None and self.index.get(line.top, -1) > j:
            return -W_IGNORED * (2 if line.heading else 1)
        return 0.0


def _skip(p: int, j: int) -> float:
    return 0.0 if p < 0 else W_SKIP * (j - p - 1)


def _viterbi(sc: _Scores, forced: dict[int, int] | None = None) -> tuple[list[int], float]:
    """The best assignment of lines to questions (-1: before the first answer) and its score. forced: question j
    must start on line u."""
    forced = forced or {}
    U, n = len(sc.lines), len(sc.numbers)
    starts_at = {u: j for j, u in forced.items()}

    def start(u: int, j: int) -> float:
        if (j in forced and forced[j] != u) or starts_at.get(u, j) != j:
            return NEG
        return sc.start(u, j)

    def stay(u: int, j: int) -> float:
        return NEG if u in starts_at else sc.stay(u, j)

    f = [[NEG] * (n + 1) for _ in range(U)]  # column j + 1 holds question j
    back: list[list[int]] = [[-2] * (n + 1) for _ in range(U)]
    f[0][0] = 0.0 if 0 not in starts_at else NEG
    for j in range(n):
        f[0][j + 1] = start(0, j) + sc.emit(0, j)
    for u in range(1, U):
        prev = f[u - 1]
        f[u][0] = prev[0] + sc.stay(u, -1) if u not in starts_at else NEG
        back[u][0] = -1
        for j in range(n):
            go_on = prev[j + 1] + stay(u, j)
            # the best way in from the title lines or an earlier question, its skips paid
            best, best_p = max([(prev[0], -1)] + [(prev[p + 1] - _skip(p, j), p) for p in range(j)])
            jump = best + start(u, j)
            if go_on >= jump:
                f[u][j + 1], back[u][j + 1] = go_on + sc.emit(u, j), j
            else:
                f[u][j + 1], back[u][j + 1] = jump + sc.emit(u, j), best_p
    last = max(range(n + 1), key=lambda c: f[U - 1][c])
    total = f[U - 1][last]
    path, j = [0] * U, last - 1
    for u in range(U - 1, -1, -1):
        path[u] = j
        j = back[u][j + 1] if u > 0 else j
    return path, total


def _max_marginals(sc: _Scores) -> dict[tuple[int, int], float]:
    """(line u, question j) -> the best score of any assignment in which question j starts on line u."""
    U, n = len(sc.lines), len(sc.numbers)
    f = [[NEG] * (n + 1) for _ in range(U)]
    fs: dict[tuple[int, int], float] = {}
    f[0][0] = 0.0
    for j in range(n):
        fs[(0, j)] = f[0][j + 1] = sc.start(0, j) + sc.emit(0, j)
    for u in range(1, U):
        prev = f[u - 1]
        f[u][0] = prev[0] + sc.stay(u, -1)
        for j in range(n):
            way_in = max([prev[0]] + [prev[p + 1] - _skip(p, j) for p in range(j)])
            fs[(u, j)] = way_in + sc.start(u, j) + sc.emit(u, j)
            f[u][j + 1] = max(prev[j + 1] + sc.stay(u, j) + sc.emit(u, j), fs[(u, j)])
    g = [[NEG] * (n + 1) for _ in range(U)]
    for c in range(n + 1):
        g[U - 1][c] = 0.0
    for u in range(U - 2, -1, -1):
        nxt = g[u + 1]
        for c in range(n + 1):
            j = c - 1
            best = nxt[c] + sc.stay(u + 1, j) + sc.emit(u + 1, j)  # emit is 0 for the title lines
            for k in range(j + 1, n):
                best = max(best, nxt[k + 1] + sc.start(u + 1, k) + sc.emit(u + 1, k) - _skip(j, k))
            g[u][c] = best
    return {(u, j): v + g[u][j + 1] for (u, j), v in fs.items() if v > NEG}


def _boundaries(path: list[int]) -> dict[int, int]:
    """question j -> the line it starts on."""
    out = {}
    for u, j in enumerate(path):
        if j >= 0 and (u == 0 or path[u - 1] != j):
            out[j] = u
    return out


def _confidence(path: list[int], total: float, marginals: dict[tuple[int, int], float]) -> dict[int, tuple[float, int | None]]:
    """question j -> (how sure its start is, 0..1, and its next-best first line)."""
    out = {}
    for j, u in _boundaries(path).items():
        others = [(v, w) for (w, k), v in marginals.items() if k == j and w != u]
        if not others:
            out[j] = (1.0, None)
            continue
        alt, w = max(others)
        margin = max(0.0, total - alt)
        out[j] = (margin / (margin + 1.0), w)
    return out


def _build(lines: list[_Line], path: list[int], sc: _Scores, exam_norms: set[str | None],
           confidence: dict[int, tuple[float, int | None]]) -> list:
    answers: list[dict] = []
    conf_by_answer: dict[int, float] = {}
    for u, (line, j) in enumerate(zip(lines, path)):
        if j < 0:
            continue
        n = sc.numbers[j]
        piece = line.text
        parts = subpart_path(line.norm)
        if u == 0 or path[u - 1] != j:
            own = line.top == n
            part = parts[0] if own and parts and f"{n}({parts[0]})" in exam_norms else None
            answers.append({"num": n, "part": part, "label": line.label if own else str(n), "texts": [],
                            "page": line.page, "bbox": line.bbox, "confs": []})
            conf_by_answer[len(answers) - 1] = round(confidence.get(j, (1.0, None))[0], 2)
            if own and parts and not part:
                piece = f"{_part_marker(parts[0])} {piece}"
            elif not own and line.label:
                piece = f"{line.label} {piece}"
        elif line.first:
            piece = continue_piece(answers, line.label, line.norm, parts, piece, line.page, line.bbox, exam_norms)
        add_text(answers[-1], piece, line.conf if line.first else None, line.page, line.bbox if line.first else None)
    return emit(answers, exam_norms, conf_by_answer)


def _key_tokens(keys: dict[str, str] | None) -> dict[int, set]:
    out: dict[int, set] = {}
    for number, text in (keys or {}).items():
        p = parent_number(str(number))
        if p.isdigit():
            out.setdefault(int(p), set()).update(tamil_format.indic_tokens(text or ""))
    return {n: t for n, t in out.items() if t}


def key_score(answers: list, keys: dict[str, str] | None) -> int:
    """Answers resembling their own question's key best, less those resembling another key more."""
    key_tokens = _key_tokens(keys)
    texts: dict[int, set] = {}
    for a in answers:
        p = parent_number(a.normalized_number or "")
        if p.isdigit():
            texts.setdefault(int(p), set()).update(tamil_format.indic_tokens(a.answer_text))
    score = 0
    for n, toks in texts.items():
        if len(toks) < MIN_TOKENS or n not in key_tokens:
            continue
        sims = {k: _similarity(toks, kt) for k, kt in key_tokens.items()}
        score += 1 if sims[n] >= max(sims.values()) - KEY_MARGIN else -1
    return score


def failing(answers: list, keys: dict[str, str] | None) -> list:
    """Answers resembling another question's key more than their own."""
    key_tokens = _key_tokens(keys)
    out = []
    for a in answers:
        p = parent_number(a.normalized_number or "")
        toks = tamil_format.indic_tokens(a.answer_text)
        if not p.isdigit() or int(p) not in key_tokens or len(toks) < MIN_TOKENS:
            continue
        sims = {k: _similarity(toks, kt) for k, kt in key_tokens.items()}
        if sims[int(p)] < max(sims.values()) - KEY_MARGIN:
            out.append(a)
    return out


def segment(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None,
            keys: dict[str, str] | None = None, repair: bool = True) -> list:
    """The sheet's answers by alignment, each with its boundary confidence; with repair, doubtful boundaries moved to
    their next-best line where that makes more answers match their own key."""
    from .answers import segment as by_numbers
    exam_norms = {getattr(q, "normalized_number", None) for q in canonical_questions or []}
    numbers: list[int] = []
    titles: dict[int, str] = {}
    for q in canonical_questions or []:
        p = parent_number(getattr(q, "normalized_number", None) or "")
        if p.isdigit() and int(p) not in titles:
            numbers.append(int(p))
            titles[int(p)] = getattr(q, "question_text", "") or ""
    lines = _lines(page_results)
    if not numbers or not lines:
        return by_numbers(page_results, canonical_questions)
    sc = _Scores(lines, numbers, titles, _key_tokens(keys))
    path, total = _viterbi(sc)
    confidence = _confidence(path, total, _max_marginals(sc))
    answers = _build(lines, path, sc, exam_norms, confidence)
    if not repair or not keys:
        return answers
    forced: dict[int, int] = {}
    best = key_score(answers, keys)
    for j, (conf, alt) in sorted(confidence.items()):
        if conf >= LOW_CONFIDENCE or alt is None:
            continue
        trial = {**forced, j: alt}
        alt_path, alt_total = _viterbi(sc, trial)
        if alt_total == NEG:
            continue
        candidate = _build(lines, alt_path, sc, exam_norms, confidence)
        if (score := key_score(candidate, keys)) > best:
            log.info("Q%s moved to its next-best start (line %d): key matches %d -> %d", numbers[j], alt, best, score)
            forced, best, answers = trial, score, candidate
    return answers


def _overlaps(a: dict | None, region: dict) -> bool:
    """a's centre lies inside region."""
    if not a:
        return False
    cx, cy = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
    return region["x"] <= cx <= region["x"] + region["width"] and region["y"] <= cy <= region["y"] + region["height"]


def _with_region(page_results: list[tuple[dict, Any]], page: int, region: dict, items: list) -> list[tuple[dict, Any]]:
    """The pages with the blocks inside region on that page replaced by items (read again, in page coordinates)."""
    out = []
    for info, res in page_results:
        if info.get("page_number") != page:
            out.append((info, res))
            continue
        kept = [b for b in res.answers if not _overlaps(b.bbox.model_dump() if b.bbox else None, region)]
        merged = kept + list(items)
        merged.sort(key=lambda b: (b.bbox.y, b.bbox.x) if b.bbox else (float("inf"), 0))
        out.append((info, res.model_copy(update={"answers": merged})))
    return out


def reread_failing(answers: list, page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None,
                   keys: dict[str, str] | None, reread: Callable[[int, dict], list] | None,
                   segment_pages: Callable[[list[tuple[dict, Any]]], list]) -> list:
    """Self-repair by reading again: each answer that resembles another question's key more than its own has its
    region read again by IndicOCR and the sheet segmented again; kept when more answers match their own key."""
    if not keys or reread is None:
        return answers
    best = key_score(answers, keys)
    for a in failing(answers, keys)[:MAX_REREADS]:
        if not a.bbox:
            continue
        items = reread(a.page_number, a.bbox)
        if not items:
            continue
        pages = _with_region(page_results, a.page_number, a.bbox, items)
        candidate = segment_pages(pages)
        if (score := key_score(candidate, keys)) > best:
            log.info("Q%s read again (page %d): key matches %d -> %d", a.normalized_number, a.page_number, best, score)
            answers, page_results, best = candidate, pages, score
    return answers
