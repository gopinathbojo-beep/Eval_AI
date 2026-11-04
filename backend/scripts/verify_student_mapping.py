"""Re-read and verify a student sheet in a SQLite snapshot; apply only with --apply.

All identifiers, question numbers and content come from the selected upload.
Original PDFs, page OCR and pre-repair grades remain in the snapshot.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models import Evaluation, AnswerSheetDocument, Exam, ExamQuestion, StudentAnswer, EvaluationItem
from app.documents.storage import abs_path, rel
from app.ocr import internvl, prompts
from app.ocr.schemas import StudentPageResult
from app.formatter.common.answers import segment_student_answers
from app.services.mapping_service import apply_student_mapping
from app import formatter


def fingerprint(rows):
    return hashlib.sha256(json.dumps([{c.name: getattr(row, c.name) for c in row.__table__.columns}
        for row in rows], sort_keys=True, default=str).encode()).hexdigest()


def answers(db, evaluation_id):
    return db.query(StudentAnswer).filter_by(evaluation_id=evaluation_id).order_by(StudentAnswer.position).all()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest_file = out / 'manifest.json'
    snapshot = out / 'source.db'
    if not manifest_file.exists():
        if engine.dialect.name != 'sqlite':
            raise SystemExit('This verification utility requires a local SQLite snapshot.')
        with SessionLocal() as db:
            ev = db.get(Evaluation, args.evaluation_id)
            if not ev:
                raise SystemExit('Evaluation not found.')
            doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
            manifest = dict(evaluation_id=ev.id, answer_hash=fingerprint(answers(db, ev.id)),
                document_hash=fingerprint([doc]), original_sha256=hashlib.sha256(abs_path(doc.original_file).read_bytes()).hexdigest())
        source = Path(engine.url.database).resolve()
        with sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True) as source_db, sqlite3.connect(snapshot) as target:
            source_db.backup(target)
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if manifest['evaluation_id'] != args.evaluation_id:
        raise SystemExit('Output directory belongs to a different evaluation.')
    with Session(create_engine('sqlite:///' + str(snapshot)), expire_on_commit=False) as db:
        ev = db.get(Evaluation, args.evaluation_id)
        exam = db.get(Exam, ev.exam_id)
        subject = formatter.for_exam(exam)
        doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
        pages = doc.pages
        qs = db.query(ExamQuestion).filter_by(exam_id=ev.exam_id).order_by(ExamQuestion.position).all()
        canonical = [f'Q{q.display_number}: {q.question_text[:200]}' for q in qs]

        def read(page):
            n = page['page_number']
            file = out / f'page-{n:03}.json'
            if not file.exists():
                # Context is source-only. No answer key or solved mathematics is supplied.
                previous = []
                earlier = next((p for p in pages if p['page_number'] == n - 1), None)
                if earlier and earlier.get('ocr_file'):
                    saved = json.loads(abs_path(earlier['ocr_file']).read_text(encoding='utf-8'))
                    previous = [dict(label=a.get('raw_question_label'), last_written_text=a.get('answer_text', '')[-400:])
                        for a in saved.get('parsed', {}).get('answers', [])[-2:]]
                prompt = prompts.student_answer_prompt(n, page['ocr_width'], page['ocr_height'], canonical, previous)
                call = internvl.chat_structured(prompts.OCR_SYSTEM, prompt, StudentPageResult, abs_path(page['processed_file']))
                file.write_text(json.dumps(dict(raw=call.raw, parsed=call.parsed.model_dump()), ensure_ascii=False, indent=2), encoding='utf-8')
            return n

        if not args.apply:
            with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 3))) as pool:
                for job in as_completed([pool.submit(read, p) for p in pages]):
                    print(f'Checked source page {job.result()}/{len(pages)}', flush=True)
        results = [(p, StudentPageResult.model_validate(json.loads((out / f"page-{p['page_number']:03}.json").read_text(encoding='utf-8'))['parsed'])) for p in pages]
        with formatter.use(subject):
            grouped = segment_student_answers(results, qs)
        # Mapping is tested on a disposable copy, retaining the source snapshot.
        working = out / ('mapping-' + uuid4().hex + '.db')
        with sqlite3.connect(snapshot) as a, sqlite3.connect(working) as b:
            a.backup(b)
    with Session(create_engine('sqlite:///' + str(working)), expire_on_commit=False) as db:
        ev = db.get(Evaluation, args.evaluation_id)
        db.query(StudentAnswer).filter_by(evaluation_id=ev.id).delete()
        for a in grouped:
            db.add(StudentAnswer(evaluation_id=ev.id, **{k: getattr(a, k) for k in (
                'raw_question_number', 'normalized_number', 'answer_text', 'raw_ocr_text', 'page_number',
                'bbox', 'ocr_confidence', 'position', 'mapping_note')}))
        db.flush()
        apply_student_mapping(db, ev)
        db.commit()
        report = [{c.name: getattr(a, c.name) for c in a.__table__.columns} for a in answers(db, ev.id)]
        (out / 'mapping-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(blocks=len(report), mapped=sum(a['status'] == 'MAPPED' for a in report),
            questions=len({a['exam_question_id'] for a in report if a['exam_question_id']}))), flush=True)
    if args.apply:
        if any(a['status'] != 'MAPPED' for a in report):
            raise SystemExit('Unresolved mappings remain; source not changed.')
        apply(args, manifest, results, subject)


def apply(args, manifest, results, subject):
    from app.services.pipeline import _build_student_answers
    from app.services.evaluation_service import _reset_item
    from app.services.audit import audit
    with SessionLocal() as db, formatter.use(subject):
        ev = db.get(Evaluation, args.evaluation_id)
        doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
        exam = db.get(Exam, ev.exam_id)
        items = db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()
        if ev.finalized_at or ev.run_status == 'RUNNING' or any(i.status == 'APPROVED' or i.teacher_overridden for i in items):
            raise SystemExit('Teacher-approved or running evaluation protected; source not changed.')
        old_answers = answers(db, ev.id)
        if fingerprint(old_answers) != manifest['answer_hash'] or fingerprint([doc]) != manifest['document_hash']:
            raise SystemExit('Source changed since verification; create a new snapshot.')
        if any(a.answer_text != a.raw_ocr_text or a.mapping_confirmed for a in old_answers):
            raise SystemExit('Teacher-edited transcription or mapping protected; source not changed.')
        original = abs_path(doc.original_file)
        assert hashlib.sha256(original.read_bytes()).hexdigest() == manifest['original_sha256']
        new_pages = []
        for p, result in results:
            saved = args.output / f"page-{p['page_number']:03}.json"
            file = original.parent / 'ocr' / f"page-{p['page_number']:03}-verified-{uuid4().hex[:10]}.json"
            file.write_text(saved.read_text(encoding='utf-8'), encoding='utf-8')
            new_pages.append({**p, 'ocr_file': rel(file), 'ocr_status': 'OK', 'ocr_error': None})
        for item in items:
            _reset_item(item)
            item.student_answer_id = None
            item.status = 'PENDING'
        ev.run_status, ev.run_progress, ev.run_total = 'IDLE', 0, 0
        ev.total_marks = ev.percentage = None
        doc.pages = new_pages
        _build_student_answers(db, doc, exam, original.parent, list(zip(new_pages, [r for _, r in results])))
        current = answers(db, ev.id)
        for item in items:
            item.student_answer_id = next((a.id for a in current if a.exam_question_id == item.exam_question_id), None)
        audit(db, exam_id=exam.id, teacher_id=exam.teacher_id, entity_type='evaluation', entity_id=ev.id,
            action='source_mapping_verified', new={'snapshot': str(args.output.resolve()), 'blocks': len(current)},
            reason='Source re-read and generic mapping corrections; previous proposals retained in source snapshot; regrading required.')
        db.commit()
        print('Applied verified transcription and mapping. Previous AI grades preserved in snapshot; regrading required.', flush=True)


if __name__ == '__main__':
    main()
