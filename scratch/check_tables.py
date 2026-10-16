import sqlite3

conn = sqlite3.connect("data/adem.db")
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in c.fetchall()]
print("Tables:", tables)

for t in ["answer_sheet_documents", "answer_sheets", "evaluations", "student_answers"]:
    if t in tables:
        c.execute(f"SELECT count(*) FROM {t}")
        print(f"{t}: {c.fetchone()[0]} rows")
        c.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in c.fetchall()]
        print(f"  columns: {cols}")
