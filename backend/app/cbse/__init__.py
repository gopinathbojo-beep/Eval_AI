"""Everything CBSE-specific: the app evaluates CBSE exams only.

formatter/  how papers, answer keys and answer sheets are read, answers mapped to questions (common/mapping.py) and
            marks checked (common/mark_rules.py, common/rubric.py); one folder per subject over common/
grading.py  the 9-point grades (A1..D2 by rank among passed students, E below the pass mark)
syllabus/   chapters and unit weightage per class and subject

The shared engine stays outside: page reading (ocr/), the job queue, evaluation and storage (services/).
"""
