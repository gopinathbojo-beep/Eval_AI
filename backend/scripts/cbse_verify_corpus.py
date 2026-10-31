"""Opt-in live extraction of all 34 supplied PDFs, with resumable per-page evidence.

Uses paid model calls. No application database, uploads or accounts are changed.
Run: python -m scripts.cbse_verify_corpus --workers 2
Results remain in ignored .e2e-data/cbse; successful pages are reused on subsequent runs.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import sys
from threading import Event
from pathlib import Path
import pymupdf
from app.cbse.catalog import PROFILES
from app.cbse.extraction import Page, SYSTEM, prompt
from app.ocr.internvl import chat_structured
from app.ocr.internvl import AIUnavailable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".e2e-data" / "cbse"
STOP = Event()


def extract(profile, kind):
    suffix = "SQP" if kind == "question-paper" else "MS"
    source = (
        ROOT
        / "exam"
        / f"Class {profile['class_level']}"
        / f"{profile['source_stem']}-{suffix}.pdf"
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = OUT / profile["id"] / suffix
    folder.mkdir(parents=True, exist_ok=True)
    results, errors, previous = [], [], []
    with pymupdf.open(source) as doc:
        for i, page in enumerate(doc, 1):
            if STOP.is_set():
                errors.append({"page": i, "error": "Provider unavailable; run stopped"})
                break
            target = folder / f"{i:03d}.json"
            cached = (
                json.loads(target.read_text(encoding="utf-8"))
                if target.exists()
                else {}
            )
            if cached.get("source_sha256") == digest and cached.get("parsed"):
                result = Page.model_validate(cached["parsed"])
            else:
                image = folder / f"{i:03d}.png"
                page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(
                    image
                )
                try:
                    call = chat_structured(
                        SYSTEM,
                        prompt(
                            kind,
                            profile,
                            i,
                            len(doc),
                            previous,
                            page.get_text(),
                            {
                                "accessibility": "standard",
                                "accountancy_option": "financial",
                            },
                        ),
                        Page,
                        image,
                    )
                    result = call.parsed
                    target.write_text(
                        json.dumps(
                            {
                                "source_sha256": digest,
                                "parsed": result.model_dump(),
                                "raw": call.raw,
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                except Exception as error:
                    if isinstance(error, AIUnavailable):
                        STOP.set()
                    errors.append({"page": i, "error": type(error).__name__})
                    print(
                        profile["id"],
                        suffix,
                        i,
                        "FAILED",
                        type(error).__name__,
                        flush=True,
                    )
                    continue
            results.append(result.model_dump())
            previous = [f.root for f in result.fragments]
            print(profile["id"], suffix, i, "OK", flush=True)
    report = {
        "profile": profile["id"],
        "kind": kind,
        "source_sha256": digest,
        "pages": results,
        "errors": errors,
    }
    (folder / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "profile": profile["id"],
        "kind": kind,
        "processed": len(results),
        "errors": len(errors),
    }


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    args.add_argument("--profile")
    opts = args.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    with ThreadPoolExecutor(max_workers=opts.workers) as executor:
        jobs = [
            executor.submit(extract, p, k)
            for p in PROFILES
            if not opts.profile or p["id"] == opts.profile
            for k in ("question-paper", "answer-key")
        ]
        for job in as_completed(jobs):
            reports.append(job.result())
            (OUT / "summary.json").write_text(
                json.dumps(reports, indent=2), encoding="utf-8"
            )
    print(json.dumps(reports, indent=2))
    sys.exit(1 if any(r["errors"] for r in reports) else 0)
