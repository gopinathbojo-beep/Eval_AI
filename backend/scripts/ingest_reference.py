"""Load the shared reference library (NCERT textbooks, CBSE marking schemes) into the app database.

    python scripts/ingest_reference.py --root "D:\\Eval_AI\\CBSE - Website" [--only 10-science] [--report]
    python scripts/ingest_reference.py --root "..\CBSE - Website" --retitle   (chapter names only)
    python scripts/ingest_reference.py --query "10-science: why does a copper vessel turn green"
    python scripts/ingest_reference.py --embed    # local vectors for passages that have none (--root does this too)
    python scripts/ingest_reference.py --export   # chunk files in data/reference/chunks/<subject>/<kind>/

Uses DATABASE_URL from backend/.env (local SQLite when empty). Only NCERT/CBSE text is read; no student data."""
import argparse, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import ReferenceChunk, ReferenceSource  # noqa: E402
from app.reference.ingest import ingest, refresh_titles  # noqa: E402
from app.reference.search import retrieve  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the 'CBSE - Website' folder; omit to only search or report")
    ap.add_argument("--only", help="limit loading to a class ('10') or subject ('10-science')")
    ap.add_argument("--report", action="store_true", help="print what the library holds per subject")
    ap.add_argument("--query", help="'<subject>: <text>', e.g. '10-science: rancidity of food'")
    ap.add_argument("--embed", action="store_true", help="embed passages without a vector (local model)")
    ap.add_argument("--export", action="store_true", help="write every passage to data/reference/chunks as JSONL")
    ap.add_argument("--retitle", action="store_true", help="with --root: re-read chapter names of loaded chapters only")
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    init_db()
    with SessionLocal() as db:
        if args.root and args.retitle:
            print(f"Chapter names refreshed for {refresh_titles(db, Path(args.root))} chapters.")
        elif args.root:
            r = ingest(db, Path(args.root), args.only)
            print(f"Loaded {len(r.loaded)} files ({r.chunks} passages), {r.unchanged} unchanged, "
                  f"{len(r.skipped)} skipped, {len(r.failed)} failed.")
            reasons = Counter(why for _, why in r.skipped)
            for why, n in reasons.most_common():
                print(f"  skipped {n}: {why}")
            for path, why in r.failed:
                print(f"  FAILED {path}: {why}")
        if args.report:
            for subject, kind, files, pages in _summary(db):
                print(f"  {subject:32} {kind:18} {files:4} files {pages:6} pages")
            print(f"  total passages: {db.query(ReferenceChunk).count()}")
        if args.root or args.embed:
            from app.reference import embed
            if embed.available():
                print(f"Embedding passages with {embed.model_name()} (local, CPU) ...", flush=True)
                n = embed.embed_missing(db, progress=lambda done: print(f"  {done} embedded", flush=True))
                print(f"Embedded {n} passages.")
            else:
                print("Embeddings skipped: install fastembed and set REFERENCE_EMBED_MODEL.")
        if args.export:
            out, files, chunks = _export(db)
            print(f"Wrote {chunks} passages in {files} files to {out}")
        if args.query:
            subject, _, text = args.query.partition(":")
            subject = subject.strip()
            for h in retrieve(db, text, int(subject.split("-")[0]), subject, k=args.k):
                print(f"\n[words {h.score:.2f} | meaning {h.similarity}] {h.title} p.{h.page_start}-{h.page_end} ({h.kind})\n{h.text[:500]}")


def _export(db):
    """One JSONL file per source, a line per passage, so the chunks can be read and checked outside the app.
    The database stays the store the app searches; these files are a copy rewritten on each export."""
    import json, re, shutil
    from app.config import get_settings
    out = get_settings().data_path / "reference" / "chunks"
    shutil.rmtree(out, ignore_errors=True)
    files = chunks = 0
    for src in db.query(ReferenceSource).order_by(ReferenceSource.subject, ReferenceSource.path):
        name = re.sub(r"[^\w.-]+", "_", src.path.replace("::", "__"))[-150:]
        target = out / src.subject / src.kind.lower() / f"{name}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = db.query(ReferenceChunk).filter_by(source_id=src.id).order_by(ReferenceChunk.id)
        with target.open("w", encoding="utf-8") as f:
            for c in rows:
                f.write(json.dumps({"id": c.id, "source": src.path, "title": src.title, "kind": c.kind,
                                    "standard": c.standard, "subject": c.subject, "chapter": c.chapter,
                                    "pages": [c.page_start, c.page_end], "question_number": c.question_number,
                                    "marks": c.marks, "criteria": c.criteria, "text": c.text},
                                   ensure_ascii=False) + "\n")
                chunks += 1
        files += 1
    return out, files, chunks


def _summary(db):
    from sqlalchemy import func
    return (db.query(ReferenceSource.subject, ReferenceSource.kind, func.count(ReferenceSource.id),
                     func.sum(ReferenceSource.pages))
            .group_by(ReferenceSource.subject, ReferenceSource.kind).order_by(ReferenceSource.subject).all())


if __name__ == "__main__":
    main()
