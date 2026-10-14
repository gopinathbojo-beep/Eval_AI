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


def extract_json_object(raw: str) -> dict:
    if raw is None:
        raise ParseError("Empty model response")
    text = raw.lstrip("\ufeff").strip()
    if not text:
        raise ParseError("Empty model response")

    # 1) the whole thing
    try:
        obj = json.loads(text)
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
            obj = json.loads(body)
            if isinstance(obj, dict):
                return _normalize_extracted_obj(obj)
        except json.JSONDecodeError:
            continue

    # 3) first balanced object embedded in prose (largest wins, to skip tiny stray {} )
    best: dict | None = None
    best_len = -1
    for cand in _balanced_candidates(text):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and len(cand) > best_len:
            best, best_len = obj, len(cand)
    if best is not None:
        return _normalize_extracted_obj(best)
    raise ParseError("No complete JSON object found in model response")
