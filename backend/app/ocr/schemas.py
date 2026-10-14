"""Pydantic schemas for model output. Strict enough to reject nonsense, lenient on types."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator


class BBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise ValueError("boolean is not a number")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {v!r}")


def _conf(v: Any) -> float | None:
    f = _num(v)
    if f is None:
        return None
    if f > 1.0 and f <= 100.0:
        f = f / 100.0
    return max(0.0, min(1.0, f))


def _str(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)


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
    _q = field_validator("raw_question_number", mode="before")(lambda cls, v: _str(v))

    @field_validator("bbox", mode="before")
    @classmethod
    def _bb(cls, v):
        return v if isinstance(v, dict) else None


class QuestionPageResult(_Base):
    page_number: int | None = None
    questions: list[QuestionItem] = Field(default_factory=list)

    @field_validator("questions", mode="before")
    @classmethod
    def _sanitize_questions(cls, v):
        if not isinstance(v, list):
            return []
        return [item for item in v if isinstance(item, (dict, QuestionItem))]


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

    @field_validator("criteria", "accepted_answers", "keywords", mode="before")
    @classmethod
    def _lst(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v]

    @field_validator("bbox", mode="before")
    @classmethod
    def _bb(cls, v):
        return v if isinstance(v, dict) else None


class AnswerKeyPageResult(_Base):
    page_number: int | None = None
    answers: list[AnswerKeyItem] = Field(default_factory=list)

    @field_validator("answers", mode="before")
    @classmethod
    def _sanitize_answers(cls, v):
        if not isinstance(v, list):
            return []
        return [item for item in v if isinstance(item, (dict, AnswerKeyItem))]


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

    @field_validator("criteria", "accepted_answers", "keywords", mode="before")
    @classmethod
    def _lst(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v]


class GeneratedAnswerKeyResult(_Base):
    answers: list[GeneratedAnswerItem] = Field(default_factory=list)


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

    @field_validator("bbox", mode="before")
    @classmethod
    def _bb(cls, v):
        if isinstance(v, dict):
            return v
        if isinstance(v, (list, tuple)) and len(v) >= 4:
            x1, y1, x2, y2 = [float(x) for x in v[:4]]
            w = max(0.0, x2 - x1) if x2 >= x1 else x2
            h = max(0.0, y2 - y1) if y2 >= y1 else y2
            return {"x": x1, "y": y1, "width": w, "height": h}
        return None

    @model_validator(mode="after")
    def _populate_defaults(self):
        if not self.question_number:
            self.question_number = self.normalized_question_label or self.raw_question_label or self.question_id
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

    @field_validator("answers", mode="before")
    @classmethod
    def _sanitize_answers(cls, v):
        if not isinstance(v, list):
            return []
        return [item for item in v if isinstance(item, (dict, StudentAnswerItem))]

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

    _n = field_validator("marks_awarded", "max_marks", mode="before")(lambda cls, v: _num(v))
    _c = field_validator("confidence", mode="before")(lambda cls, v: _conf(v))

    @field_validator("matched_points", "missing_points", mode="before")
    @classmethod
    def _lst(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v]
