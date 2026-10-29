"""Mapping accuracy without a teacher: replay every stored answer sheet and check it against its exam's key.

Read-only over data/: nothing in the database or on disk changes. For each exam of the chosen subject it rebuilds the
questions (question paper OCR), the answer keys (key OCR) and every sheet's answers (sheet OCR) with the current code,
maps the answers, and checks each sheet:

  key check     an answer mapped to Q7 must resemble key 7 more than any other key (shared content words)
  duplicates    a question answered twice
  order         answers out of the paper's order
  unmapped      answers mapped to no question
  swallowed     lines inside an answer that belong to another question's key (a boundary the OCR or the code lost)
  missing       questions with no answer: "lost" when their key text sits inside another answer, else "not written"
  key copy      a sheet that is a hand-copy of the key has a known truth: answer n is key n, no duplicates

Usage (from backend/):  python scripts/accuracy_report.py [--subject tamil] [--verbose]
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult  # noqa: E402
from app.services import paper_format  # noqa: E402
from app.formatter.common.paper import parse_question_paper_structure  # noqa: E402
from app.formatter.common.keys import segment_answer_keys  # noqa: E402
from app.formatter.common.mapping import MAPPED, map_label  # noqa: E402
from app.formatter.common.numbering import parent_number  # noqa: E402
from app.formatter.common.recovery import _tokenize  # noqa: E402
from app.formatter.common.answers import segment_student_answers  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"
MIN_TOKENS = 4      # answers shorter than this are too thin to judge against the key
KEY_MARGIN = 0.05   # own key may trail the best key by this much and still pass (near-identical keys)
KEY_COPY = 0.6      # mean answer-to-own-key similarity above this: the sheet is a copy of the key
LINE_TOKENS = 3     # a line needs this many content words to be judged on its own
LINE_OTHER = 0.5    # a line this close to another question's key ...
LINE_OWN = 0.2      # ... and this far from its own is that other question's text


def _pages(doc_dir: str, schema):
    files = sorted(glob.glob(os.path.join(doc_dir, "ocr", "page-*.json")))
    out = []
    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        if data.get("status") not in (None, "OK") or not data.get("parsed"):
            continue
        n = int(Path(f).stem.split("-")[1])
        out.append(({"page_number": n}, schema.model_validate(data["parsed"])))
    return out


def _latest(pattern: str) -> str | None:
    dirs = [d for d in glob.glob(pattern) if glob.glob(os.path.join(d, "ocr", "page-*.json"))]
    return max(dirs, key=lambda d: max(os.path.getmtime(f) for f in glob.glob(os.path.join(d, "ocr", "*.json")))) if dirs else None


def _similarity(answer: set[str], key: set[str]) -> float:
    return len(answer & key) / len(answer) if answer else 0.0


@dataclass
class SheetResult:
    exam: str
    sheet: str
    answers: int = 0
    mapped: int = 0
    key_checked: int = 0
    key_passed: int = 0
    duplicates: list[str] = field(default_factory=list)
    out_of_order: list[str] = field(default_factory=list)
    unmapped: int = 0
    missing: list[str] = field(default_factory=list)
    key_failures: list[str] = field(default_factory=list)
    swallowed: list[str] = field(default_factory=list)
    lost: list[str] = field(default_factory=list)
    key_copy: bool = False
    key_copy_errors: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.duplicates or self.out_of_order or self.unmapped or self.key_failures or self.swallowed
                    or self.lost or self.key_copy_errors)


def check_exam(exam_id: str, exam_name: str, fmt: str) -> list[SheetResult]:
    base = DATA / "exams" / exam_id
    qp_dir = _latest(str(base / "question-paper" / "*"))
    key_dir = _latest(str(base / "answer-key" / "*"))
    if not qp_dir or not key_dir:
        print(f"  {exam_name}: no question paper or key OCR stored, skipped")
        return []
    results = []
    with paper_format.use(fmt):
        qs = parse_question_paper_structure(_pages(qp_dir, QuestionPageResult)).questions
        for i, q in enumerate(qs, 1):
            q.id, q.position = f"q{q.normalized_number}", i
        keys = segment_answer_keys(_pages(key_dir, AnswerKeyPageResult), canonical_questions=qs)
        key_tokens: dict[str, set[str]] = {}
        for k in keys:
            p = parent_number(k.normalized_number or "")
            key_tokens.setdefault(p, set()).update(_tokenize(k.answer_text))
        order = {parent_number(q.normalized_number or ""): q.position for q in qs}

        for sheet_dir in sorted(glob.glob(str(base / "answer-sheets" / "*" / "*"))):
            pages = _pages(sheet_dir, StudentPageResult)
            if not pages:
                continue
            r = SheetResult(exam_name, Path(sheet_dir).name[:8])
            answers = segment_student_answers(pages, canonical_questions=qs)
            seen: dict[str, int] = {}
            last_pos, own_sims = 0, []
            holds: dict[str, str] = {}  # question whose key text sits inside another answer -> that answer
            for a in answers:
                r.answers += 1
                m = map_label(a.raw_question_number, qs, a.ocr_confidence, 0.0, answer_text=a.answer_text)
                if m.status != MAPPED or not m.normalized_number:
                    if not m.normalized_number:
                        r.unmapped += 1
                    continue
                r.mapped += 1
                p = parent_number(m.normalized_number)
                seen[p] = seen.get(p, 0) + 1
                if order.get(p, 0) < last_pos:
                    r.out_of_order.append(p)
                last_pos = max(last_pos, order.get(p, 0))
                toks = _tokenize(a.answer_text)
                if len(toks) >= MIN_TOKENS and p in key_tokens:
                    sims = {kp: _similarity(toks, kt) for kp, kt in key_tokens.items()}
                    best = max(sims, key=sims.get)
                    r.key_checked += 1
                    own_sims.append(sims[p])
                    if sims[p] >= sims[best] - KEY_MARGIN:
                        r.key_passed += 1
                    else:
                        r.key_failures.append(f"Q{p} looks like key {best} ({sims[p]:.2f} vs {sims[best]:.2f})")
                foreign: dict[str, int] = {}
                for line in a.answer_text.splitlines():
                    lt = _tokenize(line)
                    if len(lt) < LINE_TOKENS or p not in key_tokens:
                        continue
                    ls = {kp: _similarity(lt, kt) for kp, kt in key_tokens.items()}
                    other = max((kp for kp in ls if kp != p), key=ls.get, default=None)
                    if other and ls[other] >= LINE_OTHER and ls[p] < LINE_OWN:
                        foreign[other] = foreign.get(other, 0) + 1
                for other, n in foreign.items():
                    if n >= 2:
                        r.swallowed.append(f"Q{p} holds {n} lines of Q{other}")
                        holds[other] = p
            r.duplicates = [f"Q{p}" for p, n in seen.items() if n > 1]
            r.missing = [f"Q{p}" for p in order if p not in seen]
            r.lost = [f"Q{p} (inside Q{holds[p]})" for p in order if p not in seen and p in holds]
            r.key_copy = bool(own_sims) and sum(own_sims) / len(own_sims) >= KEY_COPY
            if r.key_copy:  # truth known: every question answered once, each by its own key's text
                r.key_copy_errors = r.duplicates + r.key_failures + r.swallowed
            results.append(r)
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="tamil", help="subject name contains this (default: tamil)")
    ap.add_argument("--verbose", action="store_true", help="list every failing check")
    args = ap.parse_args()
    db = sqlite3.connect(DATA / "adem.db")
    exams = [(e, n, s) for e, n, s in db.execute(
        "select e.id, e.name, s.name from exams e left join subjects s on s.id = e.subject_id")
        if args.subject.lower() in (s or "").lower()]
    all_results: list[SheetResult] = []
    for exam_id, name, subject in exams:
        fmt = paper_format.for_subject(subject)
        print(f"== {name.strip()} ({subject}, {exam_id[:8]})")
        res = check_exam(exam_id, name.strip(), fmt)
        for r in res:
            status = "OK " if r.clean else "BAD"
            tag = " [key copy]" if r.key_copy else ""
            print(f"  {status} sheet {r.sheet}{tag}: {r.mapped}/{r.answers} mapped, key check {r.key_passed}/{r.key_checked}"
                  f", missing {len(r.missing)} (lost {len(r.lost)}, not written {len(r.missing) - len(r.lost)})"
                  + (f" {r.missing}" if r.missing and args.verbose else ""))
            if args.verbose:
                for line in r.duplicates and [f"duplicates {r.duplicates}"] or []:
                    print(f"      {line}")
                if r.out_of_order:
                    print(f"      out of order {r.out_of_order}")
                if r.unmapped:
                    print(f"      unmapped answers {r.unmapped}")
                for f in r.key_failures + r.swallowed + [f"lost {x}" for x in r.lost]:
                    print(f"      {f}")
        all_results += res
    if not all_results:
        print("No sheets found.")
        return
    n = len(all_results)
    checked = sum(r.key_checked for r in all_results)
    passed = sum(r.key_passed for r in all_results)
    copies = [r for r in all_results if r.key_copy]
    print("\n== Summary")
    print(f"  sheets clean (all checks pass): {sum(r.clean for r in all_results)}/{n}")
    print(f"  answers matching their own key: {passed}/{checked} ({100 * passed / max(checked, 1):.1f}%)")
    print(f"  answers mapped: {sum(r.mapped for r in all_results)}/{sum(r.answers for r in all_results)}")
    print(f"  sheets with duplicates: {sum(bool(r.duplicates) for r in all_results)}, "
          f"out of order: {sum(bool(r.out_of_order) for r in all_results)}, "
          f"with unmapped answers: {sum(bool(r.unmapped) for r in all_results)}")
    print(f"  sheets with swallowed text: {sum(bool(r.swallowed) for r in all_results)}, "
          f"questions lost: {sum(len(r.lost) for r in all_results)}, "
          f"not written: {sum(len(r.missing) - len(r.lost) for r in all_results)}")
    if copies:
        print(f"  key-copy sheets exactly right: {sum(not r.key_copy_errors for r in copies)}/{len(copies)}")


if __name__ == "__main__":
    main()
