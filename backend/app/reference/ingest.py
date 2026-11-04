"""Loads the reference folder (CBSE - Website) into reference_sources / reference_chunks.

Text Books/Class N/<Subject>/...: NCERT chapter PDFs, loose or inside zips; *an = exercise answers.
Sample Question paper/Class N/<Paper>-MS.pdf: marking schemes (the question papers themselves are not loaded).
A file is re-read only when its sha256 changes."""
import hashlib, io, logging, re, zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from ..documents.renderer import page_text
from ..models import ReferenceChunk, ReferenceSource
from . import ncert
from .search import ensure_index

log = logging.getLogger("adem.reference")
CHUNK_CHARS, OVERLAP_CHARS = 1000, 150

# NCERT maths and science set symbols in the Symbol font, which PyMuPDF returns as U+F0xx (xx = Symbol code).
_SYMBOL = dict(zip(range(0x20, 0x7F),
                   " !∀#∃%&∋()∗+,−./0123456789:;<=>?≅ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ[∴]⊥_‾αβχδεφγηιϕκλμνοπθρστυϖωξψζ{|}∼"))
_SYMBOL.update(zip(range(0xA1, 0xE2), "ϒ′≤⁄∞ƒ♣♦♥♠↔←↑→↓°±″≥×∝∂•÷≠≡≈…|—↵ℵℑℜ℘⊗⊕∅∩∪⊃⊇⊄⊂⊆∈∉∠∇®©™∏√·¬∧∨⇔⇐⇑⇒⇓◊〈"))
_SYMBOL.update({0xE5: "∑", 0xE6: "(", 0xE9: "[", 0xEC: "{", 0xF1: "〉", 0xF2: "∫", 0xF6: ")", 0xF9: "]", 0xFC: "}"})
_PRIVATE = re.compile(r"[-�]")
_BRACE_PIECES = re.compile(r"[-]{3,}")  # under/over-braces drawn from repeated glyphs
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

_PAPER_SUBJECT = {"maths": "mathematics", "mathsbasic": "mathematics", "mathsstandard": "mathematics",
                  "appliedmaths": "applied-mathematics", "polsci": "political-science", "englishcomm": "english",
                  "englishl": "english", "englishcore": "english", "englishelective": "english",
                  "computerapplication": "computer-applications"}


def _unprivate(m: re.Match) -> str:
    code = ord(m.group())
    return _SYMBOL.get(code - 0xF000, "") if 0xF000 <= code <= 0xF0FF else ""


def clean_text(raw: str) -> str:
    raw = _PRIVATE.sub(_unprivate, _BRACE_PIECES.sub("", raw))
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in raw.splitlines())
    return "\n".join(line for line in lines if line)


def split_passages(pages: list[tuple[int, str]], size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS):
    """[(page_no, text)] -> [(page_start, page_end, passage)], cut at line ends, ~size chars, with overlap."""
    lines = [(p, line) for p, t in pages for line in t.splitlines() if line.strip()]
    out, cur, fresh = [], [], 0
    for item in lines:
        cur.append(item)
        fresh += 1
        if sum(len(l) + 1 for _, l in cur) >= size:
            out.append(cur)
            keep, n = [], 0
            for prev in reversed(cur[1:]):
                n += len(prev[1]) + 1
                if n > overlap:
                    break
                keep.insert(0, prev)
            cur, fresh = keep, 0
    if fresh:
        out.append(cur)
    return [(c[0][0], c[-1][0], "\n".join(l for _, l in c)) for c in out]


_MS_ROW = re.compile(r"^\W{0,2}(?:Q\.?\s*)?(\d{1,2})([A-Za-z](?![a-z]))?(?:[.):]\s*|\s+|$)(.*)$")
_TRAILING_MARKS = re.compile(r"\s(\d(?:\.5)?)(?:\s+\d(?:\.5)?)*\s*$")


def split_marking_scheme(pages: list[tuple[int, str]], max_chars: int = 2500):
    """Marking-scheme tables: a row starts with the question number and its first line ends with the marks
    ('13 When a nerve impulse ... 3', '10. (B) 160 cm² 1'). A new question starts only at the next number in
    sequence (or, when the line ends with marks, a small jump or the first question found), so numbered points
    inside an answer stay with it; '7B' (the OR choice)
    stays with question 7. -> [(page_start, page_end, question_number, marks, text)]; long answers are cut by size."""
    questions, cur, last = [], None, 0
    for p, line in ((p, l) for p, t in pages for l in t.splitlines() if l.strip()):
        m = _MS_ROW.match(line)
        n = int(m[1]) if m else None
        marks = _TRAILING_MARKS.search(line) if n is not None and not m[2] else None
        if n is not None and not m[2] and (n == last + 1 or (marks and (not questions or last < n <= last + 3))):
            cur = {"q": str(n), "marks": float(marks[1]) if marks else None, "lines": []}
            questions.append(cur)
            last = n
        if cur is not None:
            cur["lines"].append((p, line))
    out = []
    for q in questions:
        start = q["lines"][0][0]
        for a, b, text in split_passages(q["lines"], size=max_chars, overlap=0):
            # text far past the row's page is likely later questions the splitter missed: no number on it
            out.append((a, b, q["q"], q["marks"], text) if a <= start + 1 else (a, b, None, None, text))
    return out


def subject_key(standard: int, name: str) -> str:
    """'Hindi Course A' -> 10-hindi; 'Business Studies' or 'BusinessStudies' -> 12-business-studies."""
    base = re.sub(r"[^a-z]", "", name.lower())
    if base.startswith("hindi"):
        return f"{standard}-hindi"
    if base in _PAPER_SUBJECT:
        return f"{standard}-{_PAPER_SUBJECT[base]}"
    slug = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).lower()
    return f"{standard}-" + re.sub(r"[^a-z]+", "-", slug).strip("-")


@dataclass
class Document:
    path: str  # relative to the root; zip members as "<zip>::<member>"
    data: bytes
    kind: str
    standard: int
    subject: str
    book: str | None
    chapter: int | None = None
    question_paper: bytes | None = None  # the marking scheme's own sample paper, for the question text


@dataclass
class Report:
    loaded: list[str] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    chunks: int = 0


def _class_of(part: str) -> int | None:
    m = re.fullmatch(r"Class (\d+)", part)
    return int(m[1]) if m else None


def discover(root: Path, report: Report):
    """Yields every loadable Document under root; front matter, covers and unknown names go to report.skipped."""
    books = root / "Text Books"
    for f in sorted(books.rglob("*")) if books.exists() else []:
        parts = f.relative_to(books).parts
        standard = _class_of(parts[0]) if len(parts) >= 3 else None
        if not f.is_file() or standard is None or f.suffix.lower() not in {".pdf", ".zip"}:
            continue
        rel = f.relative_to(root).as_posix()
        subject, book = subject_key(standard, parts[1]), "/".join(parts[2:-1]) or None
        if f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as z:
                items = [(f"{rel}::{n}", n, z.read(n)) for n in sorted(z.namelist()) if n.lower().endswith(".pdf")]
        else:
            items = [(rel, f.name, None)]
        for path, name, data in items:
            meta = ncert.parse(name)
            if meta is None or meta.kind not in {"chapter", "answers", "appendix"}:
                report.skipped.append((path, "not a chapter or answers file"))
                continue
            yield Document(path, data if data is not None else f.read_bytes(),
                           "TEXTBOOK_ANSWERS" if meta.kind == "answers" else "TEXTBOOK",
                           standard, subject, book, meta.chapter)
    papers = root / "Sample Question paper"
    for f in sorted(papers.rglob("*-MS.pdf")) if papers.exists() else []:
        standard = _class_of(f.parent.name)
        if standard is not None:
            name = f.name[:-len("-MS.pdf")]
            sqp = f.with_name(f"{name}-SQP.pdf")
            yield Document(f.relative_to(root).as_posix(), f.read_bytes(), "MARKING_SCHEME", standard,
                           subject_key(standard, name), name,
                           question_paper=sqp.read_bytes() if sqp.is_file() else None)


_NOT_TITLE = re.compile(r"(?i)^(_?chapter\s*\d*|lesson\s*\d*|\d+|notes? for (the )?teachers?.*|reprint.*|mathematics|science|"
                        r".*\d{4}-\d{2}.*|(before you read|section|unit|part|theme|activity|appendix)\W*[ivx\d]*\W*)$")


_NOT_TITLE_PART = re.compile(r"(?i)sourcesforinformation|notes?for(the)?teachers?|beforeyouread")  # on letters only


def _heading(page, skip_largest: bool = False) -> str | None:
    """The chapter name: the largest-font lines on the chapter's first page. skip_largest: the largest lines are
    the book's banner (the same on every chapter), take the next size down."""
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            t = clean_text("".join(s["text"] for s in line["spans"])).strip()
            key = re.sub(r"\s+", " ", re.sub(r"[_\W]+", " ", t)).strip()
            if sum(c.isalpha() for c in t) >= 3 and not _NOT_TITLE.match(key) and not _NOT_TITLE_PART.search(re.sub(r"[\W_]+", "", t)):
                lines.append((max(s["size"] for s in line["spans"]), t))
    if not lines:
        return None
    if skip_largest:
        biggest = max(size for size, _ in lines)
        lines = [(size, t) for size, t in lines if size < biggest - 0.6]
        if not lines:
            return None
    sizes = sorted(size for size, _ in lines)
    top, body = sizes[-1], sizes[len(sizes) // 2]
    if top < body * 1.15:  # no line stands out: there is no typeset heading on this page
        return None
    picked = []
    for size, t in lines:  # headings are often printed twice (running head, shadow text)
        if size >= top - 0.6 and t not in picked:
            picked.append(t)
    words = re.sub(r"\s+", " ", " ".join(picked)).split()
    title = " ".join(w for i, w in enumerate(words) if i == 0 or w.lower() != words[i - 1].lower())
    title = re.sub(r"(?i)^chapter\s*\d+\s*:?\s*", "", title)
    title = " ".join(title.split()[:12])[:150]
    return title.title() if title.isupper() else title


def _chapter_title(doc: pymupdf.Document, number: int | None, skip_largest: bool = False) -> str | None:
    if number is None or not len(doc):
        return None
    try:
        heading = _heading(doc[0], skip_largest)
    except Exception:  # an odd page must not stop the load
        heading = None
    if heading:
        return f"Chapter {number}: {heading}"[:300]
    for line in clean_text(page_text(doc[0])).splitlines()[:12]:
        words = line.split()
        looks_like_heading = (line.isupper() or sum(w[:1].isupper() for w in words) >= 0.6 * len(words)) \
            and not line.rstrip().endswith((".", ",", ";", ":", ")"))
        if (looks_like_heading and not _NOT_TITLE.match(re.sub(r"\s+", " ", re.sub(r"[_\W]+", " ", line)).strip())
                and len(line) > 3 and len(words) <= 7 and sum(c.isalpha() for c in line) > 0.7 * len(line) and not re.match(r"(?i)chapter\b", line)
                and not _NOT_TITLE_PART.search(re.sub(r"[\W_]+", "", line))):
            return f"Chapter {number}: {line.title() if line.isupper() else line}"[:300]
    return f"Chapter {number}"


def _title(d: Document, chapter: str | None) -> str:
    if d.kind == "MARKING_SCHEME":
        return f"CBSE Class {d.standard} sample paper marking scheme ({d.book})"
    subject = d.subject.split("-", 1)[1].replace("-", " ").title()
    book = f" ({d.book})" if d.book else ""
    what = "answers" if d.kind == "TEXTBOOK_ANSWERS" else (chapter or Path(d.path).stem)
    return f"NCERT Class {d.standard} {subject}{book}: {what}"[:300]


def ingest(db: Session, root: Path, only: str | None = None) -> Report:
    """Loads (or refreshes) every document under root. only = '10' or '10-science' limits the run."""
    ensure_index(db)
    report = Report()
    sqlite = db.get_bind().dialect.name == "sqlite"
    for d in discover(root, report):
        if only and only not in {d.subject, str(d.standard)}:
            continue
        digest = hashlib.sha256(d.data + (d.question_paper or b"")).hexdigest()
        old = db.query(ReferenceSource).filter_by(path=d.path).one_or_none()
        if old is not None and old.sha256 == digest:
            report.unchanged += 1
            continue
        try:
            pdf = pymupdf.open(stream=io.BytesIO(d.data), filetype="pdf")
            pages = [(i + 1, clean_text(page_text(p))) for i, p in enumerate(pdf)]
        except Exception as e:  # one broken file must not stop the rest of the library
            report.failed.append((d.path, str(e)))
            continue
        body = "".join(t for _, t in pages)
        letters = sum(c.isalpha() for c in body)
        if letters < 40:
            report.skipped.append((d.path, "no text layer"))
            continue
        if d.subject.endswith("-hindi") and len(_DEVANAGARI.findall(body)) < 0.3 * letters:
            report.skipped.append((d.path, "legacy Hindi font: text layer is not Unicode"))
            continue
        chapter = _chapter_title(pdf, d.chapter)
        if old is not None:
            _delete_chunks(db, old, sqlite)
            db.delete(old)
            db.flush()
        src = ReferenceSource(kind=d.kind, standard=d.standard, subject=d.subject, book=d.book,
                              title=_title(d, chapter), path=d.path, sha256=digest, pages=len(pdf), issues=[])
        db.add(src)
        db.flush()
        rows = _board_rows(pages, d.question_paper) if d.kind == "MARKING_SCHEME" else []
        if d.kind == "MARKING_SCHEME" and len({q for _, _, q, _, _ in rows}) < 5:
            src.issues = ["question numbers not found; loaded as plain passages"]
            rows = []
        rows = rows or [(a, b, None, None, t) for a, b, t in split_passages(pages)]
        chunks = [ReferenceChunk(source_id=src.id, standard=d.standard, subject=d.subject, kind=d.kind,
                                 chapter=chapter, page_start=a, page_end=b, question_number=q, marks=mk, text=t)
                  for a, b, q, mk, t in rows]
        db.add_all(chunks)
        db.flush()
        if sqlite and chunks:
            db.execute(sql("INSERT INTO reference_fts(rowid, text) VALUES (:id, :text)"),
                       [{"id": c.id, "text": c.text} for c in chunks])
        db.commit()
        report.loaded.append(d.path)
        report.chunks += len(chunks)
        log.info("Reference: %s (%d passages)", d.path, len(chunks))
    if report.loaded:
        refresh_titles(db, root)  # chapter names that repeat across a book are corrected with all chapters in view
    return report


def _board_rows(ms_pages, question_paper: bytes | None):
    """Marking-scheme questions, each prefixed with its question from the sample paper when that is found."""
    asked = {}
    if question_paper:
        try:
            sqp = pymupdf.open(stream=io.BytesIO(question_paper), filetype="pdf")
            for _, _, q, marks, text in split_marking_scheme([(i + 1, clean_text(page_text(p))) for i, p in enumerate(sqp)]):
                if q and q not in asked:
                    asked[q] = (text, marks)
        except Exception as e:
            log.warning("Sample paper could not be read: %s", e)
    rows, labelled = [], set()
    for a, b, q, marks, text in split_marking_scheme(ms_pages):
        if q in asked and q not in labelled:
            labelled.add(q)
            question, q_marks = asked[q]
            text = f"QUESTION {q}: {question}\nMARKING SCHEME: {text}"
            marks = marks if marks is not None else q_marks
        rows.append((a, b, q, marks, text))
    return rows


def _delete_chunks(db: Session, src: ReferenceSource, sqlite: bool):
    ids = [i for (i,) in db.query(ReferenceChunk.id).filter_by(source_id=src.id)]
    if sqlite and ids:
        db.execute(sql("DELETE FROM reference_fts WHERE rowid = :id"), [{"id": i} for i in ids])
    db.query(ReferenceChunk).filter_by(source_id=src.id).delete()


def refresh_titles(db: Session, root: Path) -> int:
    """Re-reads the chapter names of loaded textbook chapters (without reloading their passages)."""
    found = []
    for d in discover(root, Report()):
        if d.kind != "TEXTBOOK":
            continue
        src = db.query(ReferenceSource).filter_by(path=d.path).one_or_none()
        if src is None:
            continue
        try:
            chapter = _chapter_title(pymupdf.open(stream=io.BytesIO(d.data), filetype="pdf"), d.chapter)
        except Exception:
            continue
        found.append((d, src, chapter))
    # a name shared by 3+ chapters of one book is the book's banner, not the chapter's name
    seen = Counter((d.subject, d.book, (c or "").split(": ", 1)[-1]) for d, _, c in found)
    n = 0
    for d, src, chapter in found:
        if chapter and seen[(d.subject, d.book, chapter.split(": ", 1)[-1])] >= 3:
            chapter = _chapter_title(pymupdf.open(stream=io.BytesIO(d.data), filetype="pdf"), d.chapter, True) or chapter
        if chapter:
            src.title = _title(d, chapter)
            db.query(ReferenceChunk).filter_by(source_id=src.id).update({"chapter": chapter})
            n += 1
    db.commit()
    return n
