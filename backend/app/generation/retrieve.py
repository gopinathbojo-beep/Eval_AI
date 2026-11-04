"""Retrieval for generation: the textbook passages a section is written from, and sample-paper questions of the
same marks as style examples. Scoped to one class and subject, and to the chapters the teacher picked."""
from __future__ import annotations

import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import ReferenceChunk, ReferenceSource
from ..reference.search import search

MIN_PASSAGE = 350  # shorter chunks are headings, figure captions and exercise lists


@dataclass
class Passage:
    id: int
    source_id: str
    chapter: str
    title: str
    pages: str
    text: str


def chapters(db: Session, standard: int, subject: str) -> list[dict]:
    """The textbook chapters loaded for a subject: one entry per source file."""
    rows = (db.query(ReferenceSource).filter_by(standard=standard, subject=subject, kind="TEXTBOOK")
            .order_by(ReferenceSource.book, ReferenceSource.path).all())
    out = []
    for s in rows:
        ch = db.query(ReferenceChunk.chapter).filter_by(source_id=s.id).limit(1).scalar()
        out.append({"id": s.id, "book": s.book, "chapter": ch or s.title, "title": s.title, "pages": s.pages})
    return out


def library_subjects(db: Session) -> dict[str, int]:
    """{subject key: number of textbook chapters loaded}, so the UI can tell which subjects can be generated."""
    from sqlalchemy import func
    return {k: n for k, n in db.query(ReferenceSource.subject, func.count(ReferenceSource.id))
            .filter_by(kind="TEXTBOOK").group_by(ReferenceSource.subject)}


def _passage(c: ReferenceChunk, s: ReferenceSource) -> Passage:
    pages = f"{c.page_start}" if c.page_start == c.page_end else f"{c.page_start}-{c.page_end}"
    return Passage(c.id, s.id, c.chapter or s.title, s.title, pages, c.text)


class Pool:
    """All passages of the chosen chapters; hands out a spread of unused passages per section."""

    def __init__(self, db: Session, standard: int, subject: str, source_ids: list[str] | None, topics: str = "",
                 seed: int | None = None):
        q = (db.query(ReferenceChunk, ReferenceSource).join(ReferenceSource, ReferenceSource.id == ReferenceChunk.source_id)
             .filter(ReferenceChunk.standard == standard, ReferenceChunk.subject == subject,
                     ReferenceChunk.kind.in_(["TEXTBOOK", "TEXTBOOK_ANSWERS"])))
        if source_ids:
            q = q.filter(ReferenceChunk.source_id.in_(source_ids))
        self.rng = random.Random(seed)
        by_source: dict[str, list[Passage]] = {}
        for c, s in q.all():
            if len(c.text) >= MIN_PASSAGE and c.kind == "TEXTBOOK":
                by_source.setdefault(s.id, []).append(_passage(c, s))
        for v in by_source.values():
            self.rng.shuffle(v)
        self.by_source = by_source
        self.used: set[int] = set()
        # passages matching the teacher's focus topics go first (keyword retrieval over the same scope)
        self.focus: list[Passage] = []
        if topics.strip():
            allowed = set(by_source)
            for h in search(db, topics, standard, subject, kinds=["TEXTBOOK"], k=30, min_match=0.2):
                src = next((p for ps in by_source.values() for p in ps if p.id == h.chunk_id), None)
                if src and (not source_ids or src.source_id in allowed):
                    self.focus.append(src)

    @property
    def size(self) -> int:
        return sum(len(v) for v in self.by_source.values())

    def take(self, n: int) -> list[Passage]:
        """n passages, round-robin over chapters so every chosen chapter is asked about; unused passages first."""
        picked: list[Passage] = []
        for p in self.focus:
            if len(picked) >= n // 2:
                break
            if p.id not in self.used:
                picked.append(p)
                self.used.add(p.id)
        sources = list(self.by_source)
        self.rng.shuffle(sources)
        for reuse in (False, True):
            progress = True
            while len(picked) < n and progress:
                progress = False
                for sid in sources:
                    if len(picked) >= n:
                        break
                    cand = next((p for p in self.by_source[sid] if (reuse or p.id not in self.used)
                                 and p not in picked), None)
                    if cand:
                        picked.append(cand)
                        self.used.add(cand.id)
                        progress = True
            if len(picked) >= n:
                break
        return picked


def style_examples(db: Session, standard: int, subject: str, marks: float, k: int = 3, seed: int | None = None) -> list[str]:
    """Board sample-paper questions with their marking scheme, of the same marks: how CBSE words such questions."""
    rows = (db.query(ReferenceChunk.text).filter_by(standard=standard, subject=subject, kind="MARKING_SCHEME")
            .filter(ReferenceChunk.marks == marks, ReferenceChunk.text.like("QUESTION %")).all())
    texts = [t for (t,) in rows]
    random.Random(seed).shuffle(texts)
    return [t[:1400] for t in texts[:k]]
