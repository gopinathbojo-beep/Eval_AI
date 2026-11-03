"""Keyword search over the reference library, always scoped to one class and subject.
SQLite: FTS5 (bm25). Postgres: to_tsvector('simple') with the GIN index from the migration.
A passage must contain at least min_match of the query's words, so a weak match returns nothing."""
import json, re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from ..models import ReferenceChunk, ReferenceSource

MIN_MATCH = 0.5
_STOP = set("""a an and are as at be but by can do does for from has have how in into is it its of on or that the
their them then there these this those to was were what when where which who why will with write explain describe
give state define find show prove answer question marks mark following name list any two three four five""".split())


@dataclass
class Hit:
    chunk_id: int
    score: float  # share of query words found in the passage, 0..1
    text: str
    kind: str
    chapter: str | None
    page_start: int
    page_end: int
    title: str
    path: str
    question_number: str | None = None
    marks: float | None = None


def ensure_index(db: Session):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(sql("CREATE VIRTUAL TABLE IF NOT EXISTS reference_fts USING fts5(text, "
                       "tokenize='porter unicode61 remove_diacritics 2')"))


def _stem(word: str) -> str:
    for suffix in ("ies", "ing", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def query_terms(query: str) -> list[str]:
    seen = []
    for w in re.findall(r"\w+", query.lower()):
        if (len(w) >= 3 or w.isdigit()) and w not in _STOP and w not in seen:
            seen.append(w)
    return seen[:30]


def coverage(terms: list[str], passage: str) -> float:
    if not terms:
        return 0.0
    words = {_stem(w) for w in re.findall(r"\w+", passage.lower())}
    return sum(_stem(t) in words for t in terms) / len(terms)


def search(db: Session, query: str, standard: int, subject: str, kinds: list[str] | None = None,
           k: int = 5, min_match: float = MIN_MATCH) -> list[Hit]:
    terms = query_terms(query)
    if not terms:
        return []
    scope = "c.standard = :standard AND c.subject = :subject"
    params = {"standard": standard, "subject": subject, "n": k * 8}
    if kinds:
        scope += " AND c.kind IN (" + ", ".join(f":k{i}" for i in range(len(kinds))) + ")"
        params.update({f"k{i}": kind for i, kind in enumerate(kinds)})
    if db.get_bind().dialect.name == "sqlite":
        ensure_index(db)
        params["q"] = " OR ".join(f'"{t}"' for t in terms)
        rows = db.execute(sql(f"SELECT c.id FROM reference_fts f JOIN reference_chunks c ON c.id = f.rowid "
                              f"WHERE reference_fts MATCH :q AND {scope} ORDER BY bm25(reference_fts) LIMIT :n"), params)
    else:
        params["q"] = " | ".join(terms)
        rows = db.execute(sql(f"SELECT c.id FROM reference_chunks c, to_tsquery('simple', :q) q "
                              f"WHERE to_tsvector('simple', c.text) @@ q AND {scope} "
                              f"ORDER BY ts_rank(to_tsvector('simple', c.text), q) DESC LIMIT :n"), params)
    ids = [r[0] for r in rows]
    if not ids:
        return []
    found = {c.id: (c, s) for c, s in db.query(ReferenceChunk, ReferenceSource)
             .join(ReferenceSource, ReferenceSource.id == ReferenceChunk.source_id).filter(ReferenceChunk.id.in_(ids))}
    hits = []
    for rank, i in enumerate(ids):  # keyword rank breaks ties between equal coverage
        c, s = found[i]
        score = coverage(terms, c.text)
        if score >= min_match:
            hits.append((score, -rank, Hit(c.id, round(score, 3), c.text, c.kind, c.chapter, c.page_start,
                                           c.page_end, s.title, s.path, c.question_number, c.marks)))
    return [h for *_, h in sorted(hits, key=lambda x: (x[0], x[1]), reverse=True)[:k]]


@lru_cache(maxsize=1)
def _textbook_subjects() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "cbse" / "textbook_subjects.json").read_text(encoding="utf-8"))


def subject_of(exam) -> tuple[int, str] | None:
    """(standard, library subject) for an exam from its CBSE profile, e.g. cbse-10-086 -> (10, '10-science')."""
    profile = getattr(exam, "standard_profile_id", None)
    for grade, subjects in _textbook_subjects().items():
        for s in subjects:
            if profile and profile in s.get("profiles", []):
                return int(grade), s["key"]
    # exams without a CBSE profile: the class's grade and the subject's name ('Maths', 'Social Science')
    school_class, subject = getattr(exam, "school_class", None), getattr(exam, "subject", None)
    if school_class is None or subject is None:
        return None
    try:
        from ..cbse.catalog import grade_for
        grade = grade_for(school_class)
    except (AttributeError, ValueError, TypeError):
        return None
    from .ingest import subject_key
    key = subject_key(grade, subject.name or "")
    known = {s["key"] for s in _textbook_subjects().get(str(grade), [])}
    return (grade, key) if key in known else None
