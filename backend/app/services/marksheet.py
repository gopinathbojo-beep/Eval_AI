"""
Dynamic Marksheet Generator Service for ADEM (Eval AI).
Fetches current classes, subjects, and students dynamically from the database
and generates a multi-sheet, production-grade Excel (.xlsx) workbook.

Features:
- Dynamic Classes: Generates a dedicated sheet for every class in the system.
- Dynamic Subjects: Columns adjust automatically for any subjects created in ADEM.
- Live Database Sync: Uses latest student names, roll numbers, and actual evaluation marks.
- Excel Formulas: Grand Total, Percentage, PASS/FAIL, Grade (A+, A, B, C, D, F), Class Rank.
- Bottom Statistics: Class Average, Highest, Lowest, Pass Count, Pass %.
- Consolidated Overview Sheet + Blank Template Sheet.
- Data validation & conditional formatting.
"""

from __future__ import annotations
import io
import re
from typing import Sequence
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session

from ..models import SchoolClass, Subject, Student, Exam, Evaluation

# Theme Colors (ADEM Executive Palette)
NAVY_HEADER = "1E3A8A"       # Primary deep navy header
BLUE_SUB = "3B82F6"          # Sub header blue
TEAL_HEADER = "0F766E"       # Section header teal
GRAY_BG = "F3F4F6"           # Light gray for table sub-headers
ZEBRA_ROW = "F8FAFC"         # Subtle alternating row fill
WHITE = "FFFFFF"
DARK_TEXT = "1F2937"
PASS_GREEN = "DCFCE7"        # Soft green fill
PASS_TEXT = "166534"
FAIL_RED = "FEE2E2"          # Soft red fill
FAIL_TEXT = "991B1B"
GOLD_DISTINCTION = "FEF3C7"  # Distinction gold fill
GOLD_TEXT = "92400E"
SUMMARY_BG = "E0F2FE"        # Bottom stats light cyan
BORDER_COLOR = "CBD5E1"

thin_side = Side(border_style="thin", color=BORDER_COLOR)
thick_bottom = Side(border_style="medium", color="475569")
double_bottom = Side(border_style="double", color="1E3A8A")

cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
header_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thick_bottom)
summary_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=double_bottom)


def sanitize_sheet_title(name: str) -> str:
    """Excel sheet names must be <= 31 chars and cannot contain []:*?/\\"""
    clean = re.sub(r"[\[\]:*?/\\]", "_", name.strip())
    return clean[:31] if clean else "Class"


def generate_marksheet_workbook(db: Session, teacher_id: str | None = None) -> openpyxl.Workbook:
    """
    Builds the complete multi-sheet Marksheet Excel workbook.
    """
    # 1. Fetch Classes
    class_query = db.query(SchoolClass)
    if teacher_id:
        class_query = class_query.filter_by(teacher_id=teacher_id)
    classes = class_query.order_by(SchoolClass.name).all()

    # 2. Fetch Subjects
    subject_query = db.query(Subject)
    if teacher_id:
        subject_query = subject_query.filter_by(teacher_id=teacher_id)
    subjects = subject_query.order_by(Subject.name).all()

    # Fallback if no subjects exist yet
    if not subjects:
        # Default placeholder subjects
        default_names = ["Mathematics", "Science", "English"]
        subjects = [Subject(id=f"default_{i}", name=name) for i, name in enumerate(default_names)]

    wb = openpyxl.Workbook()
    # Remove default sheet
    default_ws = wb.active
    if default_ws:
        wb.remove(default_ws)

    # Dictionary to keep sheet metadata for the Overview summary
    class_sheets_meta = []

    # 3. Build a Sheet for each Class
    for cl in classes:
        sheet_title = sanitize_sheet_title(cl.name)
        # Avoid duplicate sheet names
        idx = 2
        orig_title = sheet_title
        while sheet_title in wb.sheetnames:
            sheet_title = f"{orig_title[:28]}_{idx}"
            idx += 1

        students = db.query(Student).filter_by(class_id=cl.id).order_by(
            Student.roll_number, Student.name
        ).all()

        # Fetch evaluations for this class across subjects
        # Exam -> Evaluation map: (student_id, subject_id) -> total_marks
        exams = db.query(Exam).filter_by(class_id=cl.id).all()
        eval_map = {}
        if exams:
            exam_ids = [e.id for e in exams]
            exam_subj_map = {e.id: e.subject_id for e in exams}
            evals = db.query(Evaluation).filter(Evaluation.exam_id.in_(exam_ids)).all()
            for ev in evals:
                s_id = exam_subj_map.get(ev.exam_id)
                if s_id and ev.total_marks is not None:
                    eval_map[(ev.student_id, s_id)] = ev.total_marks

        meta = build_class_sheet(
            wb=wb,
            sheet_title=sheet_title,
            class_name=cl.name,
            students=students,
            subjects=subjects,
            eval_map=eval_map,
            is_template=False,
        )
        class_sheets_meta.append(meta)

    # Fallback if no classes exist yet: build a generic template sheet
    if not classes:
        meta = build_class_sheet(
            wb=wb,
            sheet_title="Class Roster",
            class_name="Sample Class",
            students=[],
            subjects=subjects,
            eval_map={},
            is_template=True,
        )
        class_sheets_meta.append(meta)

    # 4. Build Blank Template Sheet
    build_class_sheet(
        wb=wb,
        sheet_title="Blank Template",
        class_name="[Class Name]",
        students=[],
        subjects=subjects,
        eval_map={},
        is_template=True,
    )

    # 5. Build Consolidated Overview Sheet (Inserted as the very first sheet)
    build_overview_sheet(wb, class_sheets_meta, subjects)

    return wb


def build_class_sheet(
    wb: openpyxl.Workbook,
    sheet_title: str,
    class_name: str,
    students: Sequence[Student],
    subjects: Sequence[Subject],
    eval_map: dict,
    is_template: bool = False,
) -> dict:
    ws = wb.create_sheet(title=sheet_title)
    ws.views.sheetView[0].showGridLines = True

    num_subs = len(subjects)
    # Columns structure:
    # Col 1 (A): S.No
    # Col 2 (B): Roll No
    # Col 3 (C): Student Name
    # For each subject: 3 cols (Theory 80, Internal 20, Total 100)
    # Following subjects: Grand Total, Percentage, Result, Grade, Class Rank
    # Total columns = 3 + (num_subs * 3) + 5
    total_cols = 3 + (num_subs * 3) + 5
    last_col_letter = get_column_letter(total_cols)

    # 1. Title Banner (Rows 1 & 2)
    ws.merge_cells(f"A1:{last_col_letter}1")
    t1 = ws["A1"]
    t1.value = f"EVAL AI (ADEM) — {class_name.upper()} EXAMINATION MARK SHEET"
    t1.font = Font(name="Calibri", size=15, bold=True, color=WHITE)
    t1.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
    t1.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 38

    ws.merge_cells(f"A2:{last_col_letter}2")
    t2 = ws["A2"]
    max_grand = num_subs * 100
    t2.value = f"Academic Year: 2025–2026  |  Class: {class_name}  |  Total Subjects: {num_subs}  |  Max Marks: {max_grand}  |  Pass: Min 35% in each subject"
    t2.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    t2.fill = PatternFill(start_color=BLUE_SUB, end_color=BLUE_SUB, fill_type="solid")
    t2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    ws.row_dimensions[3].height = 8

    # 2. Main Headers (Row 4) & Sub Headers (Row 5)
    # Fixed start columns
    fixed_headers = [
        ("A", "S.No", "A4:A5"),
        ("B", "Roll No", "B4:B5"),
        ("C", "Student Name", "C4:C5"),
    ]
    for col, lbl, rng in fixed_headers:
        ws.merge_cells(rng)
        cell = ws[f"{col}4"]
        cell.value = lbl
        cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
        cell.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Subject Columns (3 cols per subject: Theory, Internal, Total)
    subject_col_triplets = []
    tot_col_letters = []

    curr_col = 4
    for sub in subjects:
        c_th = get_column_letter(curr_col)
        c_in = get_column_letter(curr_col + 1)
        c_tot = get_column_letter(curr_col + 2)
        subject_col_triplets.append((sub, c_th, c_in, c_tot))
        tot_col_letters.append(c_tot)

        # Main Header merge 3 cols
        ws.merge_cells(f"{c_th}4:{c_tot}4")
        head_cell = ws[f"{c_th}4"]
        head_cell.value = f"{sub.name.upper()} (100)"
        head_cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
        head_cell.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
        head_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Sub Headers (Row 5)
        ws[f"{c_th}5"].value = "Theory\n(80)"
        ws[f"{c_in}5"].value = "Internal\n(20)"
        ws[f"{c_tot}5"].value = "Total\n(100)"

        for c_let, is_tot in [(c_th, False), (c_in, False), (c_tot, True)]:
            scell = ws[f"{c_let}5"]
            scell.font = Font(name="Calibri", size=9, bold=True, color=NAVY_HEADER if is_tot else DARK_TEXT)
            scell.fill = PatternFill(start_color="DBEAFE" if is_tot else GRAY_BG, fill_type="solid")
            scell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        curr_col += 3

    # Summary End Columns
    c_grand = get_column_letter(curr_col)
    c_pct = get_column_letter(curr_col + 1)
    c_res = get_column_letter(curr_col + 2)
    c_grd = get_column_letter(curr_col + 3)
    c_rnk = get_column_letter(curr_col + 4)

    end_headers = [
        (c_grand, f"Grand Total\n({max_grand})", f"{c_grand}4:{c_grand}5"),
        (c_pct, "Percentage\n(%)", f"{c_pct}4:{c_pct}5"),
        (c_res, "Result", f"{c_res}4:{c_res}5"),
        (c_grd, "Grade", f"{c_grd}4:{c_grd}5"),
        (c_rnk, "Class\nRank", f"{c_rnk}4:{c_rnk}5"),
    ]
    for col, lbl, rng in end_headers:
        ws.merge_cells(rng)
        cell = ws[f"{col}4"]
        cell.value = lbl
        cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
        cell.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[4].height = 26
    ws.row_dimensions[5].height = 28

    for r in range(4, 6):
        for c in range(1, total_cols + 1):
            ws.cell(row=r, column=c).border = cell_border

    # Data Validations (Theory: 0-80, Internal: 0-20)
    theory_dv = DataValidation(type="whole", operator="between", formula1=0, formula2=80, allow_blank=True)
    internal_dv = DataValidation(type="whole", operator="between", formula1=0, formula2=20, allow_blank=True)
    ws.add_data_validation(theory_dv)
    ws.add_data_validation(internal_dv)

    start_row = 6
    num_rows = max(len(students), 15) if not is_template else 25
    end_row = start_row + num_rows - 1

    for idx in range(num_rows):
        r = start_row + idx
        sno = idx + 1
        st = students[idx] if idx < len(students) else None
        roll = st.roll_number if st else (f"{idx+1}" if (not is_template and idx < len(students)) else "")
        name = st.name if st else ""

        ws.cell(row=r, column=1, value=sno if name else "").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=r, column=2, value=roll).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=r, column=3, value=name).alignment = Alignment(horizontal="left", vertical="center")

        # Subject marks
        for sub, c_th, c_in, c_tot in subject_col_triplets:
            # If evaluated marks exist for this student and subject
            if st and (st.id, sub.id) in eval_map:
                total_ev = eval_map[(st.id, sub.id)]
                # Split roughly theory (80%) and internal (20%)
                th_val = round(min(80, total_ev * 0.8))
                in_val = round(min(20, total_ev - th_val))
                ws[f"{c_th}{r}"].value = th_val
                ws[f"{c_in}{r}"].value = in_val

            # Subject Total Formula = Theory + Internal (blank if no student name)
            ws[f"{c_tot}{r}"].value = f'=IF(ISBLANK(C{r}), "", {c_th}{r}+{c_in}{r})'
            ws[f"{c_th}{r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{c_in}{r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{c_tot}{r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{c_tot}{r}"].font = Font(name="Calibri", size=10, bold=True)

            theory_dv.add(f"{c_th}{r}")
            internal_dv.add(f"{c_in}{r}")

        # Grand Total formula: Sum of all subject totals
        sum_terms = "+".join([f"{c}{r}" for c in tot_col_letters])
        ws[f"{c_grand}{r}"].value = f'=IF(ISBLANK(C{r}), "", {sum_terms})' if sum_terms else '""'
        ws[f"{c_grand}{r}"].font = Font(name="Calibri", size=10, bold=True, color=NAVY_HEADER)
        ws[f"{c_grand}{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Percentage formula = (GrandTotal / max_grand) * 100
        ws[f"{c_pct}{r}"].value = f'=IF(OR(ISBLANK(C{r}), {c_grand}{r}=""), "", ROUND(({c_grand}{r}/{max_grand})*100, 1))'
        ws[f"{c_pct}{r}"].font = Font(name="Calibri", size=10, bold=True)
        ws[f"{c_pct}{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"{c_pct}{r}"].number_format = '0.0"%"'

        # Result formula: PASS if all subject totals >= 35, else FAIL
        pass_conds = ", ".join([f"{c}{r}>=35" for c in tot_col_letters])
        ws[f"{c_res}{r}"].value = f'=IF(OR(ISBLANK(C{r}), {c_grand}{r}=""), "", IF(AND({pass_conds}), "PASS", "FAIL"))'
        ws[f"{c_res}{r}"].font = Font(name="Calibri", size=10, bold=True)
        ws[f"{c_res}{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Grade formula:
        ws[f"{c_grd}{r}"].value = f'=IF(OR(ISBLANK(C{r}), {c_res}{r}=""), "", IF({c_res}{r}="FAIL", "F", IF({c_pct}{r}>=90, "A+", IF({c_pct}{r}>=80, "A", IF({c_pct}{r}>=70, "B", IF({c_pct}{r}>=50, "C", "D"))))))'
        ws[f"{c_grd}{r}"].font = Font(name="Calibri", size=10, bold=True)
        ws[f"{c_grd}{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Class Rank:
        ws[f"{c_rnk}{r}"].value = f'=IF(OR(ISBLANK(C{r}), {c_grand}{r}=""), "", RANK({c_grand}{r}, ${c_grand}$6:${c_grand}${end_row}))'
        ws[f"{c_rnk}{r}"].font = Font(name="Calibri", size=10, bold=True)
        ws[f"{c_rnk}{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Zebra striping & borders
        row_bg = ZEBRA_ROW if idx % 2 == 1 else WHITE
        for c in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = cell_border
            if row_bg != WHITE:
                cell.fill = PatternFill(start_color=row_bg, fill_type="solid")

    # Conditional Formatting for PASS/FAIL
    ws.conditional_formatting.add(
        f"{c_res}6:{c_res}{end_row}",
        CellIsRule(operator="equal", formula=['"PASS"'], fill=PatternFill(start_color=PASS_GREEN, fill_type="solid"), font=Font(color=PASS_TEXT, bold=True))
    )
    ws.conditional_formatting.add(
        f"{c_res}6:{c_res}{end_row}",
        CellIsRule(operator="equal", formula=['"FAIL"'], fill=PatternFill(start_color=FAIL_RED, fill_type="solid"), font=Font(color=FAIL_TEXT, bold=True))
    )
    ws.conditional_formatting.add(
        f"{c_grd}6:{c_grd}{end_row}",
        CellIsRule(operator="equal", formula=['"A+"'], fill=PatternFill(start_color=GOLD_DISTINCTION, fill_type="solid"), font=Font(color=GOLD_TEXT, bold=True))
    )

    # 3. Bottom Summary Statistics Table
    stats_start = end_row + 2
    ws.cell(row=stats_start, column=1, value="")  # gap

    stat_defs = [
        ("CLASS AVERAGE", "AVERAGE", f"{stats_start + 1}"),
        ("HIGHEST MARKS", "MAX", f"{stats_start + 2}"),
        ("LOWEST MARKS", "MIN", f"{stats_start + 3}"),
        ("TOTAL PASSED", "COUNTIF", f"{stats_start + 4}"),
        ("PASS PERCENTAGE (%)", "PASS_PCT", f"{stats_start + 5}"),
    ]

    for label, fn, r_idx_str in stat_defs:
        r = int(r_idx_str)
        ws.merge_cells(f"A{r}:C{r}")
        scell = ws[f"A{r}"]
        scell.value = label
        scell.font = Font(name="Calibri", size=9, bold=True, color=DARK_TEXT)
        scell.fill = PatternFill(start_color=SUMMARY_BG, fill_type="solid")
        scell.alignment = Alignment(horizontal="right", vertical="center")

        # Fill subject totals
        for sub, c_th, c_in, c_tot in subject_col_triplets:
            ws.merge_cells(f"{c_th}{r}:{c_tot}{r}")
            mcell = ws[f"{c_th}{r}"]
            mcell.alignment = Alignment(horizontal="center", vertical="center")
            mcell.font = Font(name="Calibri", size=9, bold=True)
            mcell.fill = PatternFill(start_color=SUMMARY_BG, fill_type="solid")

            if fn == "AVERAGE":
                mcell.value = f'=IF(COUNTA(C6:C{end_row})>0, ROUND(AVERAGE({c_tot}6:{c_tot}{end_row}), 1), "-")'
                mcell.number_format = "0.0"
            elif fn == "MAX":
                mcell.value = f'=IF(COUNTA(C6:C{end_row})>0, MAX({c_tot}6:{c_tot}{end_row}), "-")'
            elif fn == "MIN":
                mcell.value = f'=IF(COUNTA(C6:C{end_row})>0, MIN({c_tot}6:{c_tot}{end_row}), "-")'
            elif fn == "COUNTIF":
                mcell.value = f'=COUNTIF({c_tot}6:{c_tot}{end_row}, ">=35")'
            elif fn == "PASS_PCT":
                mcell.value = f'=IF(COUNTA(C6:C{end_row})>0, ROUND(({c_th}{int(r_idx_str)-1}/COUNTA(C6:C{end_row}))*100, 1), "-")'
                mcell.number_format = '0.0"%"'

        # Grand Total stat
        gcell = ws[f"{c_grand}{r}"]
        gcell.font = Font(name="Calibri", size=9, bold=True, color=NAVY_HEADER)
        gcell.alignment = Alignment(horizontal="center", vertical="center")
        gcell.fill = PatternFill(start_color=SUMMARY_BG, fill_type="solid")
        if fn == "AVERAGE":
            gcell.value = f'=IF(COUNTA(C6:C{end_row})>0, ROUND(AVERAGE({c_grand}6:{c_grand}{end_row}), 1), "-")'
            gcell.number_format = "0.0"
        elif fn == "MAX":
            gcell.value = f'=IF(COUNTA(C6:C{end_row})>0, MAX({c_grand}6:{c_grand}{end_row}), "-")'
        elif fn == "MIN":
            gcell.value = f'=IF(COUNTA(C6:C{end_row})>0, MIN({c_grand}6:{c_grand}{end_row}), "-")'
        elif fn == "COUNTIF":
            gcell.value = f'=COUNTIF({c_res}6:{c_res}{end_row}, "PASS")'
        elif fn == "PASS_PCT":
            gcell.value = f'=IF(COUNTA(C6:C{end_row})>0, ROUND(({c_grand}{int(r_idx_str)-1}/COUNTA(C6:C{end_row}))*100, 1), "-")'
            gcell.number_format = '0.0"%"'

        # Percentage stat
        pcell = ws[f"{c_pct}{r}"]
        pcell.font = Font(name="Calibri", size=9, bold=True)
        pcell.alignment = Alignment(horizontal="center", vertical="center")
        pcell.fill = PatternFill(start_color=SUMMARY_BG, fill_type="solid")
        if fn == "AVERAGE":
            pcell.value = f'=IF(COUNTA(C6:C{end_row})>0, ROUND(AVERAGE({c_pct}6:{c_pct}{end_row}), 1), "-")'
            pcell.number_format = '0.0"%"'
        elif fn == "MAX":
            pcell.value = f'=IF(COUNTA(C6:C{end_row})>0, MAX({c_pct}6:{c_pct}{end_row}), "-")'
            pcell.number_format = '0.0"%"'
        elif fn == "MIN":
            pcell.value = f'=IF(COUNTA(C6:C{end_row})>0, MIN({c_pct}6:{c_pct}{end_row}), "-")'
            pcell.number_format = '0.0"%"'

        for c in range(1, total_cols + 1):
            ws.cell(row=r, column=c).border = summary_border

    # Freeze panes below headers
    ws.freeze_panes = "D6"

    # Auto column widths
    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 11
    ws.column_dimensions["C"].width = 24
    curr_c = 4
    for _ in subjects:
        ws.column_dimensions[get_column_letter(curr_c)].width = 9
        ws.column_dimensions[get_column_letter(curr_c + 1)].width = 9
        ws.column_dimensions[get_column_letter(curr_c + 2)].width = 11
        curr_c += 3
    ws.column_dimensions[c_grand].width = 14
    ws.column_dimensions[c_pct].width = 13
    ws.column_dimensions[c_res].width = 11
    ws.column_dimensions[c_grd].width = 9
    ws.column_dimensions[c_rnk].width = 10

    return {
        "sheet_title": sheet_title,
        "class_name": class_name,
        "student_count": len(students),
        "start_row": start_row,
        "end_row": end_row,
        "c_grand": c_grand,
        "c_pct": c_pct,
        "c_res": c_res,
        "c_grd": c_grd,
        "c_rnk": c_rnk,
        "is_template": is_template,
    }


def build_overview_sheet(wb: openpyxl.Workbook, sheets_meta: list[dict], subjects: Sequence[Subject]):
    """Builds a consolidated overview dashboard comparing all classes."""
    ws = wb.create_sheet(title="Overview", index=0)
    ws.views.sheetView[0].showGridLines = True

    # Title Banner
    ws.merge_cells("A1:G1")
    t1 = ws["A1"]
    t1.value = "EVAL AI (ADEM) — INSTITUTION MARK SHEET OVERVIEW"
    t1.font = Font(name="Calibri", size=15, bold=True, color=WHITE)
    t1.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
    t1.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:G2")
    t2 = ws["A2"]
    t2.value = f"Academic Year: 2025–2026  |  Total Classes: {len(sheets_meta)}  |  Total Subjects: {len(subjects)}  |  Auto-Consolidated Dashboard"
    t2.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    t2.fill = PatternFill(start_color=BLUE_SUB, end_color=BLUE_SUB, fill_type="solid")
    t2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    # Section 1: Class Comparison Table
    ws["A4"].value = "CLASS-WISE CONSOLIDATED PERFORMANCE SUMMARY"
    ws["A4"].font = Font(name="Calibri", size=11, bold=True, color=NAVY_HEADER)

    headers = [
        ("A", "S.No"),
        ("B", "Class / Section"),
        ("C", "Total Enrolled"),
        ("D", "Passed"),
        ("E", "Failed"),
        ("F", "Pass Percentage"),
        ("G", "Class Average (%)"),
    ]

    for col, lbl in headers:
        cell = ws[f"{col}5"]
        cell.value = lbl
        cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
        cell.fill = PatternFill(start_color=TEAL_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = cell_border
    ws.row_dimensions[5].height = 24

    start_r = 6
    active_meta = [m for m in sheets_meta if not m.get("is_template")] or sheets_meta
    for i, m in enumerate(active_meta):
        r = start_r + i
        s_title = m["sheet_title"]
        s_end = m["end_row"]
        c_res = m["c_res"]
        c_pct = m["c_pct"]

        ws.cell(row=r, column=1, value=i + 1).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=r, column=2, value=m["class_name"]).alignment = Alignment(horizontal="left", vertical="center")
        # Enrolled formula = count non-empty student names in column C
        ws[f"C{r}"].value = f'=COUNTA(\'{s_title}\'!C6:C{s_end})'
        ws[f"C{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"C{r}"].font = Font(name="Calibri", size=10, bold=True)

        # Excel formulas referencing the respective class sheet:
        ws[f"D{r}"].value = f'=COUNTIF(\'{s_title}\'!{c_res}6:{c_res}{s_end}, "PASS")'
        ws[f"D{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"D{r}"].font = Font(name="Calibri", size=10, bold=True, color=PASS_TEXT)

        ws[f"E{r}"].value = f'=COUNTIF(\'{s_title}\'!{c_res}6:{c_res}{s_end}, "FAIL")'
        ws[f"E{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"E{r}"].font = Font(name="Calibri", size=10, bold=True, color=FAIL_TEXT)

        ws[f"F{r}"].value = f'=IF(C{r}>0, ROUND((D{r}/C{r})*100, 1), 0)'
        ws[f"F{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"F{r}"].font = Font(name="Calibri", size=10, bold=True)
        ws[f"F{r}"].number_format = '0.0"%"'

        ws[f"G{r}"].value = f'=IF(C{r}>0, ROUND(AVERAGE(\'{s_title}\'!{c_pct}6:{c_pct}{s_end}), 1), 0)'
        ws[f"G{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"G{r}"].font = Font(name="Calibri", size=10, bold=True, color=NAVY_HEADER)
        ws[f"G{r}"].number_format = '0.0"%"'

        for c in range(1, 8):
            cell = ws.cell(row=r, column=c)
            cell.border = cell_border
            if i % 2 == 1:
                cell.fill = PatternFill(start_color=ZEBRA_ROW, fill_type="solid")

    # Column widths
    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 13
    ws.column_dimensions["E"].width = 13
    ws.column_dimensions["F"].width = 18
    ws.column_dimensions["G"].width = 20


def generate_marksheet_bytes(db: Session, teacher_id: str | None = None) -> io.BytesIO:
    """Generates the workbook and returns it as an in-memory BytesIO stream."""
    wb = generate_marksheet_workbook(db, teacher_id=teacher_id)
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def sync_root_marksheet_file(db: Session, teacher_id: str | None = None) -> bool:
    """
    Safely writes the dynamically updated workbook to Student_Marksheet.xlsx in the project root.
    If the file is locked open in Excel, saves to Student_Marksheet_Updated.xlsx as a fallback.
    """
    try:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        if os.environ.get("DATA_DIR"):  # explicit data dir (e.g. the test suite): keep the project root untouched
            from ..config import get_settings
            base_dir = str(get_settings().data_path)
        target_path = os.path.join(base_dir, "Student_Marksheet.xlsx")
        stream = generate_marksheet_bytes(db, teacher_id=teacher_id)
        data = stream.getvalue()
        try:
            with open(target_path, "wb") as f:
                f.write(data)
            return True
        except (PermissionError, IOError):
            fallback_path = os.path.join(base_dir, "Student_Marksheet_Updated.xlsx")
            with open(fallback_path, "wb") as f:
                f.write(data)
            return True
    except Exception:
        return False
