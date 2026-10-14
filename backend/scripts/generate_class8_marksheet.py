"""
Script to generate Class_8_Student_Marksheet.xlsx for ADEM (Eval AI).
Dynamically fetches all classes, subjects, students, and evaluation marks from the database.
"""

from __future__ import annotations
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal
from app.services.marksheet import generate_marksheet_workbook

OUTPUT_PATH = os.path.join(backend_dir, "..", "Class_8_Student_Marksheet.xlsx")


def main():
    db = SessionLocal()
    try:
        wb = generate_marksheet_workbook(db)
        out_file = os.path.abspath(OUTPUT_PATH)
        try:
            wb.save(out_file)
            print(f"Generated dynamic marksheet with sheets: {wb.sheetnames}")
            print(f"Saved to: {out_file}")
        except PermissionError:
            fallback = os.path.normpath(os.path.join(backend_dir, "..", "Class_8_Student_Marksheet_Updated.xlsx"))
            wb.save(fallback)
            print(f"Note: 'Class_8_Student_Marksheet.xlsx' is currently open in Excel.")
            print(f"Saved updated marksheet to: {fallback}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
