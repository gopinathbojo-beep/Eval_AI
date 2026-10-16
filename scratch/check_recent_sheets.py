import sqlite3

conn = sqlite3.connect("data/adem.db")
c = conn.cursor()
c.execute("SELECT id, exam_id, original_filename, status, stage, uploaded_at FROM answer_sheet_documents ORDER BY uploaded_at DESC LIMIT 5")
for r in c.fetchall():
    print(r)
