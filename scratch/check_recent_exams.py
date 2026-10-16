import sqlite3

conn = sqlite3.connect("data/adem.db")
c = conn.cursor()
c.execute("SELECT id, name, academic_year, status, total_marks, created_at FROM exams ORDER BY created_at DESC LIMIT 5")
for r in c.fetchall():
    print(r)
