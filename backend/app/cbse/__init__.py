"""Everything CBSE-specific: the app evaluates CBSE exams only.

class10/subjects/<subject>/  one folder per subject of the standard: its formatter (__init__.py), its paper design
class12/subjects/<subject>/  (format.json) and, when added, its syllabus (syllabus.json)
common/                      what every class and subject shares: reading papers, keys and answer sheets (paper.py,
                             keys.py, answers.py), mapping answers to questions (mapping.py), marks and rubrics
                             (mark_rules.py, rubric.py), paper designs (standards.py), the 9-point grades
                             (grading.py), syllabus loading (syllabus.py)
common/subjects/<subject>/   a subject's rules every class shares (tamil/, english/, maths/, physics/, chemistry/)
formatter.py                 which of these folders reads and grades a given exam

The shared engine stays outside: page reading (ocr/), the job queue, evaluation and storage (services/).
"""
