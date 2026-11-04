"""Re-extract one exam in an isolated SQLite/file snapshot; never update the source exam."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def run_copy(manifest_path, retry_failed=False):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    from app.database import SessionLocal, engine
    from app.config import get_settings
    from app.models import Exam, QuestionPaperDocument, AnswerKeyDocument, ExamQuestion, AnswerKey
    from app.services.pipeline import process_document
    from app.services.extracted_pdf import exam_extraction_report_pdf
    from app.documents.storage import abs_path, rel
    from app.cbse.extraction import Page
    from app.ocr.internvl import extract_json_object

    if (Path(engine.url.database).resolve() != (manifest_path.parent / "app.db").resolve()
            or get_settings().data_path.resolve() != (manifest_path.parent / "data").resolve()):
        raise SystemExit("Refusing to run outside the isolated database and file directory.")

    with SessionLocal() as db:
        for kind, model in (("question-paper", QuestionPaperDocument), ("answer-key", AnswerKeyDocument)):
            entry = manifest[kind]
            doc = db.get(model, entry["id"])
            doc.original_file = entry["copy_path"]
            if not retry_failed:
                doc.pages = []
                doc.status = "UPLOADED"
            else:
                # Revalidate the saved raw responses with the current parser.
                # Only this snapshot is changed; invalid pages are reread below.
                pages = [dict(page) for page in doc.pages]
                for page in pages:
                    if page.get("ocr_status") == "FAILED_PARSE":
                        continue  # Exercise the production retry/recovery path.
                    cache = abs_path(doc.original_file).parent / "ocr" / f"page-{page['page_number']:03d}.json"
                    if not cache.exists():
                        continue
                    data = json.loads(cache.read_text(encoding="utf-8"))
                    try:
                        parsed = data.get("parsed") or extract_json_object(data.get("raw", ""))
                        if "fragments" not in parsed:
                            continue
                        result = Page.model_validate(parsed)
                    except (ValueError, TypeError):
                        continue
                    data.update(status="OK", parsed=result.model_dump())
                    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                    page.update(ocr_status="OK", ocr_error=None, ocr_file=rel(cache))
                doc.pages = pages
            db.commit()
    with SessionLocal() as db:
        paper_ready = db.get(QuestionPaperDocument, manifest["question-paper"]["id"]).status == "READY"
    if not retry_failed or not paper_ready:
        print("Reading question paper in isolated copy", flush=True)
        process_document("question-paper", manifest["question-paper"]["id"], retry_failed)
    # Adopting a profile automatically queues the copied marking scheme. If
    # it was already a structured exam, read the copied scheme explicitly.
    with SessionLocal() as db:
        key_doc = db.get(AnswerKeyDocument, manifest["answer-key"]["id"])
        ready = key_doc.status == "READY"
    if not ready:
        print("Reading marking scheme in isolated copy", flush=True)
        process_document("answer-key", manifest["answer-key"]["id"], True)
    with SessionLocal() as db:
        exam = db.get(Exam, manifest["exam_id"])
        paper = db.get(QuestionPaperDocument, manifest["question-paper"]["id"])
        scheme = db.get(AnswerKeyDocument, manifest["answer-key"]["id"])
        questions = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
        keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()
        summary = {"profile": exam.standard_profile_id, "paper_status": paper.status,
                   "scheme_status": scheme.status, "paper_error": paper.error_message,
                   "scheme_error": scheme.error_message, "question_count": len(questions),
                   "key_count": len(keys),
                   "questions_requiring_review": [{"number": q.display_number, "reason": q.review_reason}
                                                  for q in questions if q.verification_status == "NEEDS_REVIEW"],
                   "keys_requiring_review": [{"number": k.raw_question_number,
                       "reason": "; ".join(filter(None, [k.mapping_note, *(k.rubric or {}).get("problems", [])]))}
                       for k in keys if k.mapping_status != "MAPPED" or (k.rubric or {}).get("problems")]}
        summary["fresh_extraction_verified"] = paper.status == "READY" and scheme.status == "READY"
        (manifest_path.parent / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if summary["fresh_extraction_verified"]:
            (manifest_path.parent / "Extraction_Report.pdf").write_bytes(
                exam_extraction_report_pdf(exam, paper, scheme, questions, keys))
        print(json.dumps({k: v for k, v in summary.items() if not k.endswith("requiring_review")}, indent=2), flush=True)
        if not summary["fresh_extraction_verified"]:
            raise SystemExit("Fresh extraction could not be verified; summary.json contains diagnostics, not accepted new results.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-id")
    parser.add_argument("--run-copy", type=Path)
    parser.add_argument("--resume-copy", type=Path)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if args.run_copy:
        run_copy(args.run_copy.resolve(), args.retry_failed)
        return
    if args.resume_copy:
        manifest_path = args.resume_copy.resolve()
        if not manifest_path.is_relative_to(BACKEND / ".verification"):
            parser.error("Resume requires a manifest inside backend/.verification")
        launch_copy(manifest_path, True)
        return
    if not args.exam_id:
        parser.error("--exam-id is required")
    from app.database import SessionLocal, engine
    from app.documents.storage import abs_path
    from app.config import get_settings
    from app.models import QuestionPaperDocument, AnswerKeyDocument
    if engine.dialect.name != "sqlite":
        raise SystemExit("This verification utility requires a local SQLite source.")
    target = BACKEND / ".verification" / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True)
    manifest = {"exam_id": args.exam_id}
    with SessionLocal() as db:
        for kind, model in (("question-paper", QuestionPaperDocument), ("answer-key", AnswerKeyDocument)):
            doc = db.query(model).filter_by(exam_id=args.exam_id, is_active=True).first()
            if not doc:
                raise SystemExit(f"No active {kind} upload found")
            source = abs_path(doc.original_file)
            relative = (source.relative_to(get_settings().data_path.resolve()) if args.retry_failed
                        else Path("uploads") / kind / source.name)
            destination = target / "data" / relative
            destination.parent.mkdir(parents=True)
            if args.retry_failed:
                shutil.copytree(source.parent, destination.parent, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            manifest[kind] = {"id": doc.id, "copy_path": relative.as_posix()}
    with sqlite3.connect(Path(engine.url.database).resolve().as_uri() + "?mode=ro", uri=True) as source_db:
        with sqlite3.connect(target / "app.db") as copy_db:
            source_db.backup(copy_db)
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    launch_copy(manifest_path, args.retry_failed)


def launch_copy(manifest_path, retry_failed=False):
    target = manifest_path.parent
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{(target / 'app.db').as_posix()}",
           "DATA_DIR": str(target / "data"), "STORAGE_PROVIDER": "local", "DURABLE_JOBS": "false",
           "JOB_QUEUE_INLINE": "true", "AUTO_MIGRATE": "false"}
    print(f"Isolated verification: {target}", flush=True)
    command = [sys.executable, str(Path(__file__).resolve()), "--run-copy", str(manifest_path)]
    if retry_failed:
        command.append("--retry-failed")
    subprocess.run(command,
                   cwd=BACKEND, env=env, check=True)


if __name__ == "__main__":
    main()
