"""
Script to generate Class_8_Student_Marksheet.xlsx for ADEM (Eval AI).
Fetches enrolled students from data/adem.db and builds:
  1. Consolidated Overview Sheet
  2. Class 8-A Sheet
  3. Class 8-B Sheet
  4. Class 8-C Sheet
  5. Blank Template Sheet
Features:
  - 5 Core Subjects: Tamil, English, Mathematics, Science, Social Science
  - Theory (80) + Internal (20) breakdown -> Subject Total (100)
  - Grand Total (500), Percentage (%), Result (PASS/FAIL), Grade (A+, A, B, C, D, F), Rank
  - Bottom summary statistics (Class Average, Highest, Lowest, Pass Count, Pass %)
  - Data Validation: Theory (0-80), Internal (0-20)
  - Conditional Formatting: PASS (soft green), FAIL (soft red), Distinction (soft gold)
  - Freeze Panes & Auto Column Widths
"""

import os
import sqlite3
import random
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "adem.db")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Class_8_Student_Marksheet.xlsx")

# Theme Colors
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

def get_students_by_class():
    if not os.path.exists(DB_PATH):
        return {
            "8-A": [("20", "Nila"), ("21", "Gopinath"), ("22", "lisa"), ("23", "bala")],
            "8-B": [("20", "Aran"), ("21", "Harish"), ("22", "Diya"), ("23", "Oviya")],
            "8-C": [("20", "Riya"), ("21", "Arul"), ("22", "praveen"), ("23", "Rohith")],
        }
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute("""
        SELECT cl.name, s.roll_number, s.name 
        FROM students s 
        JOIN classes cl ON s.class_id = cl.id 
        WHERE cl.name LIKE '8%'
        ORDER BY cl.name, CAST(s.roll_number AS INTEGER), s.name
    """).fetchall()
    conn.close()

    res = {}
    for cl_name, roll, name in rows:
        res.setdefault(cl_name, []).append((roll, name))
    return res

def build_section_sheet(wb, sheet_name, title_suffix, students, is_template=False):
    ws = wb.create_sheet(title=sheet_name)
    ws.views.sheetView[0].showGridLines = True

    # 1. Title Banner (Rows 1 & 2)
    ws.merge_cells("A1:W1")
    title_cell = ws["A1"]
    title_cell.value = "EVAL AI (ADEM) — CLASS 8 ANNUAL EXAMINATION MARK SHEET"
    title_cell.font = Font(name="Calibri", size=16, bold=True, color=WHITE)
    title_cell.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 42

    ws.merge_cells("A2:W2")
    sub_cell = ws["A2"]
    sub_cell.value = f"Academic Year: 2025–2026  |  Section: {title_suffix}  |  Max Marks: 500  |  Pass Criteria: Minimum 35% in each subject"
    sub_cell.font = Font(name="Calibri", size=11, bold=True, color=WHITE)
    sub_cell.fill = PatternFill(start_color=BLUE_SUB, end_color=BLUE_SUB, fill_type="solid")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 24

    ws.row_dimensions[3].height = 10  # blank gap

    # 2. Main Headers (Row 4) & Sub Headers (Row 5)
    headers_main = [
        ("A", "S.No", "A4:A5"),
        ("B", "Roll No", "B4:B5"),
        ("C", "Student Name", "C4:C5"),
        ("D", "TAMIL (100)", "D4:F4"),
        ("G", "ENGLISH (100)", "G4:I4"),
        ("J", "MATHEMATICS (100)", "J4:L4"),
        ("M", "SCIENCE (100)", "M4:O4"),
        ("P", "SOCIAL SCIENCE (100)", "P4:R4"),
        ("S", "Grand Total (500)", "S4:S5"),
        ("T", "Percentage (%)", "T4:T5"),
        ("U", "Result", "U4:U5"),
        ("V", "Grade", "V4:V5"),
        ("W", "Class Rank", "W4:W5"),
    ]

    for col_letter, label, merge_range in headers_main:
        ws.merge_cells(merge_range)
        cell = ws[f"{col_letter}4"]
        cell.value = label
        cell.font = Font(name="Calibri", size=11, bold=True, color=WHITE)
        cell.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Sub-headers (Row 5) for subjects
    sub_cols = [
        ("D", "Theory\n(80)"), ("E", "Internal\n(20)"), ("F", "Total\n(100)"),
        ("G", "Theory\n(80)"), ("H", "Internal\n(20)"), ("I", "Total\n(100)"),
        ("J", "Theory\n(80)"), ("K", "Internal\n(20)"), ("L", "Total\n(100)"),
        ("M", "Theory\n(80)"), ("N", "Internal\n(20)"), ("O", "Total\n(100)"),
        ("P", "Theory\n(80)"), ("Q", "Internal\n(20)"), ("R", "Total\n(100)"),
    ]

    for col_letter, label in sub_cols:
        cell = ws[f"{col_letter}5"]
        cell.value = label
        is_tot = "Total" in label
        cell.font = Font(name="Calibri", size=10, bold=True, color=NAVY_HEADER if is_tot else DARK_TEXT)
        cell.fill = PatternFill(start_color="DBEAFE" if is_tot else GRAY_BG, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[4].height = 28
    ws.row_dimensions[5].height = 32

    # Border for header rows
    for r in range(4, 6):
        for c in range(1, 24):
            ws.cell(row=r, column=c).border = cell_border

    # Data Validation Rules
    theory_dv = DataValidation(
        type="whole",
        operator="between",
        formula1=0,
        formula2=80,
        allow_blank=True,
        showInputMessage=True,
        promptTitle="Theory Marks",
        prompt="Enter marks between 0 and 80",
        showErrorMessage=True,
        errorTitle="Invalid Theory Marks",
        error="Theory marks must be between 0 and 80.",
    )
    internal_dv = DataValidation(
        type="whole",
        operator="between",
        formula1=0,
        formula2=20,
        allow_blank=True,
        showInputMessage=True,
        promptTitle="Internal Marks",
        prompt="Enter marks between 0 and 20",
        showErrorMessage=True,
        errorTitle="Invalid Internal Marks",
        error="Internal / Practical marks must be between 0 and 20.",
    )
    ws.add_data_validation(theory_dv)
    ws.add_data_validation(internal_dv)

    random.seed(42 + hash(sheet_name) % 100)

    start_row = 6
    num_students = len(students) if not is_template else 25
    end_row = start_row + num_students - 1

    subjects_cols = [("D", "E", "F"), ("G", "H", "I"), ("J", "K", "L"), ("M", "N", "O"), ("P", "Q", "R")]

    for idx in range(num_students):
        r = start_row + idx
        sno = idx + 1
        roll = students[idx][0] if idx < len(students) else (f"{idx+1}" if not is_template else "")
        name = students[idx][1] if idx < len(students) else ""

        ws.cell(row=r, column=1, value=sno).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=r, column=2, value=roll).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=r, column=3, value=name).alignment = Alignment(horizontal="left", vertical="center")

        # Subject marks
        for sub_th, sub_in, sub_tot in subjects_cols:
            if not is_template and name:
                th_val = random.randint(50, 76)
                in_val = random.randint(15, 20)
                ws[f"{sub_th}{r}"].value = th_val
                ws[f"{sub_in}{r}"].value = in_val

            ws[f"{sub_tot}{r}"].value = f"={sub_th}{r}+{sub_in}{r}"
            ws[f"{sub_th}{r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{sub_in}{r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{sub_tot}{r}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{sub_tot}{r}"].font = Font(name="Calibri", size=11, bold=True)

            # Link cells to Data Validation
            theory_dv.add(f"{sub_th}{r}")
            internal_dv.add(f"{sub_in}{r}")

        # Grand Total S = F + I + L + O + R
        ws[f"S{r}"].value = f"=F{r}+I{r}+L{r}+O{r}+R{r}"
        ws[f"S{r}"].font = Font(name="Calibri", size=11, bold=True, color=NAVY_HEADER)
        ws[f"S{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Percentage T = (S / 500) * 100
        ws[f"T{r}"].value = f"=ROUND((S{r}/500)*100, 1)"
        ws[f"T{r}"].font = Font(name="Calibri", size=11, bold=True)
        ws[f"T{r}"].alignment = Alignment(horizontal="center", vertical="center")
        ws[f"T{r}"].number_format = '0.0"%"'

        # Result U: PASS if all subject totals >= 35 else FAIL
        ws[f"U{r}"].value = f'=IF(AND(F{r}>=35, I{r}>=35, L{r}>=35, O{r}>=35, R{r}>=35), "PASS", "FAIL")'
        ws[f"U{r}"].font = Font(name="Calibri", size=11, bold=True)
        ws[f"U{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Grade V:
        ws[f"V{r}"].value = f'=IF(U{r}="FAIL", "F", IF(T{r}>=90, "A+", IF(T{r}>=80, "A", IF(T{r}>=70, "B", IF(T{r}>=50, "C", "D")))))'
        ws[f"V{r}"].font = Font(name="Calibri", size=11, bold=True)
        ws[f"V{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Class Rank W:
        ws[f"W{r}"].value = f'=IF(ISBLANK(C{r}), "", RANK(S{r}, $S$6:$S${end_row}))'
        ws[f"W{r}"].font = Font(name="Calibri", size=11, bold=True)
        ws[f"W{r}"].alignment = Alignment(horizontal="center", vertical="center")

        # Row style & borders
        row_bg = ZEBRA_ROW if idx % 2 == 1 else WHITE
        for c in range(1, 24):
            cell = ws.cell(row=r, column=c)
            cell.border = cell_border
            if row_bg != WHITE:
                cell.fill = PatternFill(start_color=row_bg, fill_type="solid")

        ws.row_dimensions[r].height = 23

    # Conditional Formatting for Result (Column U) & Percentage (Column T)
    pass_rule = CellIsRule(
        operator="equal",
        formula=['"PASS"'],
        stopIfTrue=True,
        fill=PatternFill(start_color=PASS_GREEN, end_color=PASS_GREEN, fill_type="solid"),
        font=Font(name="Calibri", color=PASS_TEXT, bold=True),
    )
    fail_rule = CellIsRule(
        operator="equal",
        formula=['"FAIL"'],
        stopIfTrue=True,
        fill=PatternFill(start_color=FAIL_RED, end_color=FAIL_RED, fill_type="solid"),
        font=Font(name="Calibri", color=FAIL_TEXT, bold=True),
    )
    distinction_rule = CellIsRule(
        operator="greaterThanOrEqual",
        formula=["75"],
        stopIfTrue=False,
        fill=PatternFill(start_color=GOLD_DISTINCTION, end_color=GOLD_DISTINCTION, fill_type="solid"),
        font=Font(name="Calibri", color=GOLD_TEXT, bold=True),
    )

    ws.conditional_formatting.add(f"U6:U{end_row}", pass_rule)
    ws.conditional_formatting.add(f"U6:U{end_row}", fail_rule)
    ws.conditional_formatting.add(f"T6:T{end_row}", distinction_rule)

    # Bottom Summary Statistics (Class Average, Highest, Lowest, Pass Count, Pass %)
    stat_rows = [
        ("Class Average", "AVERAGE"),
        ("Highest Marks (Max)", "MAX"),
        ("Lowest Marks (Min)", "MIN"),
        ("Pass Count (>= 35)", "COUNTIF"),
        ("Pass Percentage (%)", "PASS_PCT"),
    ]

    cur_r = end_row + 2
    for stat_label, stat_op in stat_rows:
        ws.merge_cells(f"A{cur_r}:C{cur_r}")
        label_cell = ws[f"A{cur_r}"]
        label_cell.value = stat_label
        label_cell.font = Font(name="Calibri", size=10, bold=True, color=NAVY_HEADER)
        label_cell.alignment = Alignment(horizontal="right", vertical="center")

        all_metric_cols = [
            "D", "E", "F", "G", "H", "I", "J", "K", "L",
            "M", "N", "O", "P", "Q", "R", "S", "T"
        ]

        for col in all_metric_cols:
            c_cell = ws[f"{col}{cur_r}"]
            c_cell.font = Font(name="Calibri", size=10, bold=True)
            c_cell.alignment = Alignment(horizontal="center", vertical="center")

            if stat_op == "AVERAGE":
                c_cell.value = f"=ROUND(AVERAGE({col}6:{col}{end_row}), 1)"
                if col == "T":
                    c_cell.number_format = '0.0"%"'
            elif stat_op == "MAX":
                c_cell.value = f"=MAX({col}6:{col}{end_row})"
                if col == "T":
                    c_cell.number_format = '0.0"%"'
            elif stat_op == "MIN":
                c_cell.value = f"=MIN({col}6:{col}{end_row})"
                if col == "T":
                    c_cell.number_format = '0.0"%"'
            elif stat_op == "COUNTIF":
                if col in ["F", "I", "L", "O", "R"]:
                    c_cell.value = f'=COUNTIF({col}6:{col}{end_row}, ">=35")'
                elif col in ["S", "T"]:
                    c_cell.value = f'=COUNTIF(U6:U{end_row}, "PASS")'
            elif stat_op == "PASS_PCT":
                if col in ["F", "I", "L", "O", "R"]:
                    c_cell.value = f'=ROUND((COUNTIF({col}6:{col}{end_row}, ">=35") / COUNTA(C6:C{end_row})) * 100, 1)'
                    c_cell.number_format = '0.0"%"'
                elif col in ["S", "T"]:
                    c_cell.value = f'=ROUND((COUNTIF(U6:U{end_row}, "PASS") / COUNTA(C6:C{end_row})) * 100, 1)'
                    c_cell.number_format = '0.0"%"'

        # Overall Result & Grade summary
        if stat_op == "COUNTIF":
            ws[f"U{cur_r}"].value = f'=COUNTIF(U6:U{end_row}, "PASS") & " Passed"'
            ws[f"U{cur_r}"].font = Font(name="Calibri", size=10, bold=True, color=PASS_TEXT)
            ws[f"U{cur_r}"].alignment = Alignment(horizontal="center", vertical="center")
        elif stat_op == "PASS_PCT":
            ws[f"U{cur_r}"].value = f'=ROUND((COUNTIF(U6:U{end_row}, "PASS")/COUNTA(C6:C{end_row}))*100, 1) & "%"'
            ws[f"U{cur_r}"].font = Font(name="Calibri", size=10, bold=True, color=PASS_TEXT)
            ws[f"U{cur_r}"].alignment = Alignment(horizontal="center", vertical="center")

        for c in range(1, 24):
            cell = ws.cell(row=cur_r, column=c)
            cell.border = summary_border if stat_op == "PASS_PCT" else cell_border
            cell.fill = PatternFill(start_color=SUMMARY_BG, fill_type="solid")

        ws.row_dimensions[cur_r].height = 22
        cur_r += 1

    # Freeze panes on C (Roll No and Name always visible when scrolling right)
    ws.freeze_panes = "D6"

    # Set column widths nicely
    col_widths = {
        "A": 8, "B": 12, "C": 22,
        "D": 11, "E": 11, "F": 13,
        "G": 11, "H": 11, "I": 13,
        "J": 11, "K": 11, "L": 13,
        "M": 11, "N": 11, "O": 13,
        "P": 11, "Q": 11, "R": 13,
        "S": 18, "T": 15, "U": 13, "V": 10, "W": 12,
    }
    for col_l, w in col_widths.items():
        ws.column_dimensions[col_l].width = w

    return ws

def build_overview_sheet(wb, class_names):
    ws = wb.create_sheet(title="Consolidated Overview", index=0)
    ws.views.sheetView[0].showGridLines = True

    # 1. Main Header Banner
    ws.merge_cells("A1:I1")
    t1 = ws["A1"]
    t1.value = "EVAL AI (ADEM) — CLASS 8 CONSOLIDATED PERFORMANCE OVERVIEW"
    t1.font = Font(name="Calibri", size=16, bold=True, color=WHITE)
    t1.fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
    t1.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 42

    ws.merge_cells("A2:I2")
    t2 = ws["A2"]
    t2.value = "Academic Year: 2025–2026  |  Total Sections: 3 (8-A, 8-B, 8-C)  |  Standard: Class 8  |  Subjects: 5 Core (500 Marks)"
    t2.font = Font(name="Calibri", size=11, bold=True, color=WHITE)
    t2.fill = PatternFill(start_color=BLUE_SUB, end_color=BLUE_SUB, fill_type="solid")
    t2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 24

    ws.row_dimensions[3].height = 14

    # 2. Section Performance Comparison Table
    headers = [
        ("A", "Class Section"),
        ("B", "Enrolled Students"),
        ("C", "Tamil Avg"),
        ("D", "English Avg"),
        ("E", "Maths Avg"),
        ("F", "Science Avg"),
        ("G", "Social Avg"),
        ("H", "Class Avg (%)"),
        ("I", "Overall Pass %"),
    ]

    ws.row_dimensions[4].height = 30
    for col_letter, label in headers:
        cell = ws[f"{col_letter}4"]
        cell.value = label
        cell.font = Font(name="Calibri", size=11, bold=True, color=WHITE)
        cell.fill = PatternFill(start_color=TEAL_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = cell_border

    row_idx = 5
    for cl in class_names:
        sheet_ref = f"'Class {cl}'"
        ws.cell(row=row_idx, column=1, value=f"Class {cl}").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=2, value=f"=COUNTA({sheet_ref}!C6:C25)").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=3, value=f"=ROUND(AVERAGE({sheet_ref}!F6:F25), 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=4, value=f"=ROUND(AVERAGE({sheet_ref}!I6:I25), 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=5, value=f"=ROUND(AVERAGE({sheet_ref}!L6:L25), 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=6, value=f"=ROUND(AVERAGE({sheet_ref}!O6:O25), 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=7, value=f"=ROUND(AVERAGE({sheet_ref}!R6:R25), 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=row_idx, column=8, value=f"=ROUND(AVERAGE({sheet_ref}!T6:T25), 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws[f"H{row_idx}"].number_format = '0.0"%"'
        ws.cell(row=row_idx, column=9, value=f"=ROUND((COUNTIF({sheet_ref}!U6:U25, \"PASS\")/COUNTA({sheet_ref}!C6:C25))*100, 1)").alignment = Alignment(horizontal="center", vertical="center")
        ws[f"I{row_idx}"].number_format = '0.0"%"'

        for c in range(1, 10):
            cell = ws.cell(row=row_idx, column=c)
            cell.border = cell_border
            cell.font = Font(name="Calibri", size=11, bold=(c in [1, 8, 9]))
            if row_idx % 2 == 1:
                cell.fill = PatternFill(start_color=ZEBRA_ROW, fill_type="solid")

        ws.row_dimensions[row_idx].height = 24
        row_idx += 1

    # Class 8 Total Combined Row
    ws.cell(row=row_idx, column=1, value="Class 8 Overall").alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=row_idx, column=2, value=f"=SUM(B5:B{row_idx-1})").alignment = Alignment(horizontal="center", vertical="center")
    for c in range(3, 8):
        col_l = get_column_letter(c)
        ws.cell(row=row_idx, column=c, value=f"=ROUND(AVERAGE({col_l}5:{col_l}{row_idx-1}), 1)").alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=row_idx, column=8, value=f"=ROUND(AVERAGE(H5:H{row_idx-1}), 1)").alignment = Alignment(horizontal="center", vertical="center")
    ws[f"H{row_idx}"].number_format = '0.0"%"'
    ws.cell(row=row_idx, column=9, value=f"=ROUND(AVERAGE(I5:I{row_idx-1}), 1)").alignment = Alignment(horizontal="center", vertical="center")
    ws[f"I{row_idx}"].number_format = '0.0"%"'

    for c in range(1, 10):
        cell = ws.cell(row=row_idx, column=c)
        cell.border = summary_border
        cell.font = Font(name="Calibri", size=11, bold=True, color=NAVY_HEADER)
        cell.fill = PatternFill(start_color=SUMMARY_BG, fill_type="solid")
    ws.row_dimensions[row_idx].height = 26

    # Grading Scale Reference Table
    row_idx += 3
    ws.merge_cells(f"A{row_idx}:E{row_idx}")
    g_title = ws[f"A{row_idx}"]
    g_title.value = "OFFICIAL GRADING SCHEME & CRITERIA"
    g_title.font = Font(name="Calibri", size=11, bold=True, color=WHITE)
    g_title.fill = PatternFill(start_color=NAVY_HEADER, fill_type="solid")
    g_title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row_idx].height = 26

    grading_rows = [
        ("Grade", "Mark Range (%)", "Description", "Status", "Remarks"),
        ("A+", "90% – 100%", "Outstanding Performance", "PASS", "Distinction with Honours"),
        ("A", "80% – 89%", "Excellent Mastery", "PASS", "Distinction"),
        ("B", "70% – 79%", "Very Good", "PASS", "First Class"),
        ("C", "50% – 69%", "Good Understanding", "PASS", "Second Class"),
        ("D", "35% – 49%", "Satisfactory / Pass", "PASS", "Eligible for Promotion"),
        ("F", "Below 35%", "Needs Immediate Remedial Support", "FAIL", "Supplementary Exam Required"),
    ]

    for r_offset, g_data in enumerate(grading_rows):
        cur_r = row_idx + 1 + r_offset
        for c_idx, val in enumerate(g_data):
            cell = ws.cell(row=cur_r, column=c_idx + 1, value=val)
            is_head = r_offset == 0
            cell.font = Font(name="Calibri", size=10, bold=is_head or (c_idx == 0))
            cell.alignment = Alignment(horizontal="center" if c_idx in [0, 1, 3] else "left", vertical="center")
            cell.border = cell_border
            if is_head:
                cell.fill = PatternFill(start_color="E5E7EB", fill_type="solid")
            elif val == "FAIL":
                cell.fill = PatternFill(start_color=FAIL_RED, fill_type="solid")
                cell.font = Font(name="Calibri", size=10, bold=True, color=FAIL_TEXT)
            elif val == "PASS":
                cell.fill = PatternFill(start_color=PASS_GREEN, fill_type="solid")
                cell.font = Font(name="Calibri", size=10, bold=True, color=PASS_TEXT)
        ws.row_dimensions[cur_r].height = 20

    # Column widths
    ov_widths = {"A": 18, "B": 18, "C": 14, "D": 14, "E": 14, "F": 14, "G": 14, "H": 16, "I": 16}
    for col_l, w in ov_widths.items():
        ws.column_dimensions[col_l].width = w

    return ws

def main():
    wb = openpyxl.Workbook()
    default_sheet = wb.active

    students_by_class = get_students_by_class()

    # Build Class 8-A, 8-B, 8-C
    for cl_name, st_list in students_by_class.items():
        build_section_sheet(wb, f"Class {cl_name}", f"Class {cl_name}", st_list)

    # Build Blank Template
    build_section_sheet(wb, "Blank Template", "Class 8 [New Section]", [], is_template=True)

    # Build Overview Sheet
    build_overview_sheet(wb, list(students_by_class.keys()))

    if default_sheet in wb.worksheets:
        wb.remove(default_sheet)

    wb.save(OUTPUT_PATH)
    print(f"Successfully generated: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
