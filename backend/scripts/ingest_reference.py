"""Load the shared reference library (NCERT textbooks, CBSE marking schemes) into the app database.

    python scripts/ingest_reference.py --root "D:\\Eval_AI\\CBSE - Website" [--only 10-science] [--report]
    python scripts/ingest_reference.py --query "10-science: why does a copper vessel turn green"

Uses DATABASE_URL from backend/.env (local SQLite when empty). Only NCERT/CBSE text is read; no student data."""
import argparse, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import ReferenceChunk, ReferenceSource  # noqa: E402
from app.reference.ingest import ingest  # noqa: E402
from app.reference.search import search  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the 'CBSE - Website' folder; omit to only search or report")
    ap.add_argument("--only", help="limit loading to a class ('10') or subject ('10-science')")
    ap.add_argument("--report", action="store_true", help="print what the library holds per subject")
    ap.add_argument("--query", help="'<subject>: <text>', e.g. '10-science: rancidity of food'")
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    init_db()
    with SessionLocal() as db:
        if args.root:
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
        if args.query:
            subject, _, text = args.query.partition(":")
            subject = subject.strip()
            for h in search(db, text, int(subject.split("-")[0]), subject, k=args.k):
                print(f"\n[{h.score:.2f}] {h.title} p.{h.page_start}-{h.page_end} ({h.kind})\n{h.text[:500]}")


def _summary(db):
    from sqlalchemy import func
    return (db.query(ReferenceSource.subject, ReferenceSource.kind, func.count(ReferenceSource.id),
                     func.sum(ReferenceSource.pages))
            .group_by(ReferenceSource.subject, ReferenceSource.kind).order_by(ReferenceSource.subject).all())


if __name__ == "__main__":
    main()
