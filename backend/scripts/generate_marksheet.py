"""
CLI script to dynamically generate the complete ADEM Marksheet (.xlsx) workbook.
Automatically queries all classes, subjects, students, and evaluation marks from the database.
Usage:
    python backend/scripts/generate_marksheet.py
"""

from __future__ import annotations
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal
from app.services.marksheet import generate_marksheet_workbook

OUTPUT_PATH = os.path.join(backend_dir, "..", "Student_Marksheet.xlsx")

def main():
    print("=" * 60)
    print("  ADEM (Eval AI) — Dynamic Marksheet Generator")
    print("=" * 60)
    db = SessionLocal()
    try:
        print("Fetching classes, subjects, students, and evaluated marks...")
        wb = generate_marksheet_workbook(db)
        out_file = os.path.abspath(OUTPUT_PATH)
        try:
            wb.save(out_file)
            print(f"\nSUCCESS! Generated workbook with sheets: {wb.sheetnames}")
            print(f"Saved to:\n  {out_file}\n")
        except PermissionError:
            fallback = os.path.normpath(os.path.join(backend_dir, "..", "Student_Marksheet_Updated.xlsx"))
            wb.save(fallback)
            print(f"\nNote: 'Student_Marksheet.xlsx' is currently open in Excel.")
            print(f"Saved updated marksheet to:\n  {fallback}\n")
            print("To update 'Student_Marksheet.xlsx', please close Microsoft Excel and re-run.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
