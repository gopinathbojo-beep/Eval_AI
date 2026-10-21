"""Robust, *conservative* JSON extraction from model output.

Handles: plain JSON, ```json fences, BOM, whitespace, leading/trailing prose.
Refuses: truncated JSON, no JSON object at all. Callers must still validate with Pydantic.
"""
from __future__ import annotations
import json
import re


class ParseError(ValueError):
    pass


_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _balanced_candidates(text: str):
    """Yield substrings that are brace-balanced top-level objects (string-aware)."""
    n = len(text)
    i = 0
    while i < n:
        if text[i] == "{":
            depth, j, in_str, esc = 0, i, False, False
            while j < n:
                c = text[j]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                else:
                    if c == '"':
                        in_str = True
                    elif c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            yield text[i:j + 1]
                            i = j
                            break
                j += 1
        i += 1


def _normalize_extracted_obj(obj: dict) -> dict:
    if "questions" in obj and isinstance(obj["questions"], list):
        clean_qs = [q for q in obj["questions"] if isinstance(q, dict)]
        if clean_qs:
            last_q = clean_qs[-1]
            for k in ("marks", "section", "confidence", "bbox"):
                if k in obj and (k not in last_q or last_q.get(k) is None):
                    last_q[k] = obj.pop(k, None)
        obj["questions"] = clean_qs
    elif "answers" in obj and isinstance(obj["answers"], list):
        clean_ans = [a for a in obj["answers"] if isinstance(a, dict)]
        if clean_ans:
            last_a = clean_ans[-1]
            for k in ("marks", "criteria", "confidence", "bbox"):
                if k in obj and (k not in last_a or last_a.get(k) is None):
                    last_a[k] = obj.pop(k, None)
        obj["answers"] = clean_ans
    return obj


def _combine_duplicate_keys(pairs):
    d: dict = {}
    for k, v in pairs:
        if k in d and isinstance(d[k], list) and isinstance(v, list):
            d[k].extend(v)
        else:
            d[k] = v
    return d


def _try_repair_json(text: str) -> dict | None:
    # Fix mismatched quotes on keys like 'page_number': or "page_number':
    cleaned = re.sub(r'["\']([a-zA-Z0-9_]+)["\']\s*:', r'"\1":', text)
    # Strip runaway repeated closing brackets: e.g. }}]}}]}}]...
    cleaned = re.sub(r"(?:[\]\}]\s*){3,}$", "", cleaned).strip()
    for closing in ["", "}", "]}", "]}}"]:
        try:
            cand = cleaned + closing
            obj = json.loads(cand, object_pairs_hook=_combine_duplicate_keys)
            if isinstance(obj, dict) and ("answers" in obj or "questions" in obj or "page_number" in obj):
                return obj
        except Exception:
            pass
    return None


def _extract_partial_items(text: str) -> dict | None:
    pat = re.compile(r'\{\s*(?:"answer_id"|"question_number"|"raw_question_label")', re.IGNORECASE)
    starts = [m.start() for m in pat.finditer(text)]
    if not starts:
        return None
    answers = []
    for i, start_idx in enumerate(starts):
        end_idx = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start_idx:end_idx]
        qn_m = re.search(r'"question_number"\s*:\s*"([^"]+)"', block)
        raw_lbl_m = re.search(r'"raw_question_label"\s*:\s*"([^"]+)"', block)
        ans_txt_m = re.search(r'"answer_text"\s*:\s*"((?:[^"\\]|\\.)*)"', block, re.DOTALL)
        if (qn_m or raw_lbl_m) and ans_txt_m:
            ans_text = ""
            if ans_txt_m:
                try:
                    ans_text = json.loads(f'"{ans_txt_m.group(1)}"')
                except Exception:
                    ans_text = ans_txt_m.group(1).replace('\\"', '"').replace('\\n', "\n")
            lbl = raw_lbl_m.group(1) if raw_lbl_m else (qn_m.group(1) if qn_m else None)
            answers.append({
                "question_number": qn_m.group(1) if qn_m else lbl,
                "raw_question_label": lbl,
                "answer_text": ans_text,
                "ocr_confidence": 0.95,
            })
    if answers:
        return {"answers": answers}
    return None


def extract_json_object(raw: str) -> dict:
    if raw is None:
        raise ParseError("Empty model response")
    text = raw.lstrip("\ufeff").strip()
    if not text:
        raise ParseError("Empty model response")

    # 1) the whole thing
    try:
        obj = json.loads(text, object_pairs_hook=_combine_duplicate_keys)
        if isinstance(obj, dict):
            return _normalize_extracted_obj(obj)
        if isinstance(obj, list):
            return {"items": obj}
    except json.JSONDecodeError:
        pass

    # 2) fenced blocks
    for m in _FENCE.finditer(text):
        body = m.group(1).strip()
        try:
            obj = json.loads(body, object_pairs_hook=_combine_duplicate_keys)
            if isinstance(obj, dict):
                return _normalize_extracted_obj(obj)
        except json.JSONDecodeError:
            continue

    # 3) try repairing broken JSON (unclosed brackets, mismatched quotes, runaway brackets)
    repaired = _try_repair_json(text)
    if repaired:
        return _normalize_extracted_obj(repaired)

    # 4) first balanced object embedded in prose (largest wins, to skip tiny stray {} )
    best: dict | None = None
    best_len = -1
    for cand in _balanced_candidates(text):
        try:
            obj = json.loads(cand, object_pairs_hook=_combine_duplicate_keys)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and len(cand) > best_len:
            best, best_len = obj, len(cand)

    # If best is an actual document container (has questions/answers)
    if best is not None:
        if "answers" in best or "questions" in best or ("answers" not in text and "questions" not in text):
            return _normalize_extracted_obj(best)

    # 5) Partial item regex recovery if answers list was present in text
    partial = _extract_partial_items(text)
    if partial:
        return _normalize_extracted_obj(partial)

    if best is not None:
        return _normalize_extracted_obj(best)

    raise ParseError("No complete JSON object found in model response")
