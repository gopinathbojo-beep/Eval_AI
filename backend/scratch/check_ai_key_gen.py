import sys
import os
sys.path.insert(0, os.path.abspath("."))

import time
import json
from app.database import SessionLocal
from app.models import Teacher, Exam
from app.routes.answer_keys import generate_answer_keys_ai

db = SessionLocal()
t = db.query(Teacher).first()
e = db.query(Exam).filter_by(id="ae5f5aa7-6cbf-421e-aefe-eff6cbcf9905").first()

print(f"Starting AI generation for {e.name} with 10 questions...")
t0 = time.time()
try:
    res = generate_answer_keys_ai(e.id, db=db, t=t)
    answers = res.get("answers", [])
    print(f"Done in {time.time() - t0:.2f}s! Generated answers count: {len(answers)}")
    for ans in answers[:3]:
        print(f"  Q{ans['question_number']}: {ans['answer_text'][:80]}... (marks={ans['marks']})")
    with open("scratch/generated_keys.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
except Exception as exc:
    print(f"Exception after {time.time() - t0:.2f}s:", exc)
finally:
    db.close()
