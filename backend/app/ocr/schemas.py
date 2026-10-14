"""Pydantic schemas for model output. Strict enough to reject nonsense, lenient on types."""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator


class BBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}
_CONF_WORDS = {"very high": 0.95, "high": 0.9, "medium": 0.6, "moderate": 0.6, "low": 0.3, "very low": 0.1}


def _num(v: Any) -> float | None:
    """Lenient number: 5, "5", "5 marks", "2+1", "1½". Unreadable -> None (never fails the whole page)."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for k in ("value", "total", "marks", "score"):
            if k in v:
                return _num(v[k])
        return None
    t = str(v).strip()
    for ch, val in _FRACTIONS.items():
        t = re.sub(rf"(\d*)\s*{ch}", lambda m, val=val: str((float(m.group(1)) if m.group(1) else 0) + val), t)
    try:
        return float(t)
    except ValueError:
        pass
    if re.fullmatch(r"\s*\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)+\s*(?:marks?|m)?\s*", t, re.I):
        return float(sum(float(x) for x in _NUM_RE.findall(t)))
    m = _NUM_RE.search(t)
    return float(m.group()) if m else None


def _awarded(v: Any) -> float | None:
    """Marks awarded by the evaluator: '2/5' -> 2 (score out of max), otherwise as _num."""
    if isinstance(v, str):
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*/\s*\d+(?:\.\d+)?", v)
        if m:
            return float(m.group(1))
    return _num(v)


def _conf(v: Any) -> float | None:
    if isinstance(v, str):
        w = v.strip().lower()
        if w in _CONF_WORDS:
            return _CONF_WORDS[w]
        v = w.rstrip("%")
    f = _num(v)
    if f is None:
        return None
    if f > 1.0 and f <= 100.0:
        f = f / 100.0
    return max(0.0, min(1.0, f))


def _str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v if x is not None)
    s = str(v).strip()
    return s or None


def _text(v: Any) -> str:
    """Free-text field: never None. Lists of lines/blocks are joined, not lost."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return "\n".join(t for t in (_text(x) for x in v) if t)
    if isinstance(v, dict):
        for k in ("text", "raw_text", "content", "value", "answer", "point"):
            if v.get(k):
                return _text(v[k])
        return " ".join(str(x) for x in v.values() if isinstance(x, (str, int, float)))
    return str(v)


def _str_list(v: Any) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, (str, dict)):
        v = [v]
    return [t for t in (_text(x).strip() for x in v) if t]


def _bbox(v: Any) -> dict | None:
    """Accept {x,y,width,height}, {x,y,w,h}, {x1,y1,x2,y2} or [x1,y1,x2,y2]. Anything else -> None."""
    try:
        if isinstance(v, dict):
            if all(k in v for k in ("x", "y", "width", "height")):
                return {k: float(v[k]) for k in ("x", "y", "width", "height")}
            if all(k in v for k in ("x", "y", "w", "h")):
                return {"x": float(v["x"]), "y": float(v["y"]), "width": float(v["w"]), "height": float(v["h"])}
            if not all(k in v for k in ("x1", "y1", "x2", "y2")):
                return None
            v = [v["x1"], v["y1"], v["x2"], v["y2"]]
        if isinstance(v, (list, tuple)) and len(v) >= 4:
            x1, y1, x2, y2 = [float(x) for x in v[:4]]
            if x2 > x1 and y2 > y1:
                return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
            return {"x": x1, "y": y1, "width": x2, "height": y2}
    except (TypeError, ValueError):
        return None
    return None


def _page(v: Any) -> int | None:
    f = _num(v)
    return int(f) if f is not None else None


def _alias(data: Any, target: str, *aliases: str) -> Any:
    """Copy the first present alias key into `target` when the model used a different field name."""
    if isinstance(data, dict) and not data.get(target):
        for a in aliases:
            if data.get(a):
                data = dict(data)
                data[target] = data[a]
                break
    return data


def _list_root(data: Any, target: str, *aliases: str) -> Any:
    """Page results: accept a bare list, or the item list under another common key."""
    if isinstance(data, list):
        return {target: data}
    data = _alias(data, target, *aliases)
    if isinstance(data, dict) and isinstance(data.get(target), dict):
        data = dict(data)
        data[target] = [data[target]]
    return data


class _Base(BaseModel):
    model_config = {"extra": "ignore"}


class QuestionItem(_Base):
    raw_question_number: str | None = None
    question_text: str = ""
    question_type: str | None = None
    marks: float | None = None
    section: str | None = None
    confidence: float | None = None
    bbox: BBox | None = None

    _n = field_validator("marks", mode="before")(lambda cls, v: _num(v))
    _c = field_validator("confidence", mode="before")(lambda cls, v: _conf(v))
    _q = field_validator("raw_question_number", "question_type", "section", mode="before")(lambda cls, v: _str(v))
    _t = field_validator("question_text", mode="before")(lambda cls, v: _text(v))

    @model_validator(mode="before")
    @classmethod
    def _aliases(cls, data):
        data = _alias(data, "question_text", "text", "question", "content")
        return _alias(data, "raw_question_number", "question_number", "number", "label", "q_no")

    _bb = field_validator("bbox", mode="before")(lambda cls, v: _bbox(v))


class QuestionPageResult(_Base):
    page_number: int | None = None
    questions: list[QuestionItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _root(cls, data):
        return _list_root(data, "questions", "items", "question_list", "data")

    _p = field_validator("page_number", mode="before")(lambda cls, v: _page(v))


class AnswerKeyItem(_Base):
    question_number: str | None = None
    answer_text: str = ""
    marks: float | None = None
    criteria: list[str] = Field(default_factory=list)
    accepted_answers: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    confidence: float | None = None
    bbox: BBox | None = None

    _n = field_validator("marks", mode="before")(lambda cls, v: _num(v))
    _c = field_validator("confidence", mode="before")(lambda cls, v: _conf(v))
    _q = field_validator("question_number", mode="before")(lambda cls, v: _str(v))
    _t = field_validator("answer_text", mode="before")(lambda cls, v: _text(v))

    @model_validator(mode="before")
    @classmethod
    def _aliases(cls, data):
        data = _alias(data, "answer_text", "answer", "text", "model_answer", "solution")
        return _alias(data, "question_number", "raw_question_number", "number", "label", "q_no")

    _lst = field_validator("criteria", "accepted_answers", "keywords", mode="before")(lambda cls, v: _str_list(v))

    _bb = field_validator("bbox", mode="before")(lambda cls, v: _bbox(v))


class AnswerKeyPageResult(_Base):
    page_number: int | None = None
    answers: list[AnswerKeyItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _root(cls, data):
        return _list_root(data, "answers", "items", "questions", "answer_key", "data")

    _p = field_validator("page_number", mode="before")(lambda cls, v: _page(v))


class GeneratedAnswerItem(_Base):
    exam_question_id: str | None = None
    question_number: str | None = None
    answer_text: str = ""
    marks: float | None = None
    criteria: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    accepted_answers: list[str] = Field(default_factory=list)

    _m = field_validator("marks", mode="before")(lambda cls, v: _num(v))
    _q = field_validator("question_number", "exam_question_id", mode="before")(lambda cls, v: _str(v))
    _t = field_validator("answer_text", mode="before")(lambda cls, v: _text(v))

    _lst = field_validator("criteria", "accepted_answers", "keywords", mode="before")(lambda cls, v: _str_list(v))


class GeneratedAnswerKeyResult(_Base):
    answers: list[GeneratedAnswerItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _root(cls, data):
        return _list_root(data, "answers", "items", "questions", "data")


class StudentAnswerItem(_Base):
    question_number: str | None = None
    raw_question_label: str | None = None
    normalized_question_label: str | None = None
    question_id: str | None = None
    answer_id: str | None = None
    mapping_status: str | None = None
    answer_text: str = ""
    ocr_confidence: float | None = None
    question_number_confidence: float | None = None
    grouping_confidence: float | None = None
    mapping_confidence: float | None = None
    content_blocks: list[Any] = Field(default_factory=list)
    bbox: BBox | None = None
    page_number: int | None = None
    evidence: dict | None = None

    _c = field_validator("ocr_confidence", "question_number_confidence", "grouping_confidence", "mapping_confidence", mode="before")(lambda cls, v: _conf(v))
    _q = field_validator("question_number", "raw_question_label", "normalized_question_label", "question_id", "answer_id", "mapping_status", mode="before")(lambda cls, v: _str(v))

    _bb = field_validator("bbox", mode="before")(lambda cls, v: _bbox(v))
    _t = field_validator("answer_text", mode="before")(lambda cls, v: _text(v))
    _p = field_validator("page_number", mode="before")(lambda cls, v: _page(v))

    @model_validator(mode="before")
    @classmethod
    def _aliases(cls, data):
        data = _alias(data, "answer_text", "text", "answer", "student_answer", "transcription")
        return _alias(data, "question_number", "label", "question_label", "q_no")

    @model_validator(mode="after")
    def _populate_defaults(self):
        # The label as written on the sheet is the evidence; a model-"corrected" label is only a guess
        # (e.g. Q17 -> Q1) and must go through the app's recovery/review path instead of auto-mapping.
        if self.raw_question_label:
            self.question_number = self.raw_question_label
        elif not self.question_number:
            self.question_number = self.normalized_question_label or self.question_id
        if not self.raw_question_label:
            self.raw_question_label = self.question_number
        if not self.answer_text and self.content_blocks:
            texts = []
            for b in self.content_blocks:
                if isinstance(b, dict):
                    t = b.get("text") or b.get("raw_text") or ""
                    if t:
                        texts.append(t)
                elif isinstance(b, str) and b:
                    texts.append(b)
            if texts:
                self.answer_text = "\n".join(texts)
        if self.ocr_confidence is None:
            self.ocr_confidence = self.mapping_confidence
        return self


class StudentPageResult(_Base):
    page_number: int | None = None
    page: int | None = None
    answers: list[StudentAnswerItem] = Field(default_factory=list)
    unresolved: list[Any] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _root(cls, data):
        return _list_root(data, "answers", "items", "responses", "blocks", "data")

    _p = field_validator("page_number", "page", mode="before")(lambda cls, v: _page(v))

    @model_validator(mode="after")
    def _sync_page(self):
        if self.page_number is None and self.page is not None:
            self.page_number = self.page
        return self


class EvaluationResult(_Base):
    marks_awarded: float
    max_marks: float | None = None
    decision: str | None = None
    matched_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    feedback: str = ""
    confidence: float | None = None

    _n = field_validator("marks_awarded", mode="before")(lambda cls, v: _awarded(v))
    _mm = field_validator("max_marks", mode="before")(lambda cls, v: _num(v))
    _c = field_validator("confidence", mode="before")(lambda cls, v: _conf(v))

    _lst = field_validator("matched_points", "missing_points", mode="before")(lambda cls, v: _str_list(v))
    _f = field_validator("feedback", mode="before")(lambda cls, v: _text(v))
    _d = field_validator("decision", mode="before")(lambda cls, v: _str(v))
