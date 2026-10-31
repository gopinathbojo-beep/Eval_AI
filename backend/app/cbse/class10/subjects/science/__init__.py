"""Class 10 Science (086): its paper design is format.json beside this file (39 questions, 80 marks; Section A
Biology 1-16, B Chemistry 17-29, C Physics 30-39). Reading and grading use the shared rules (common/).

The layout of the 2026-27 sample paper, all of it handled in common/ because every CBSE paper shares it
(tests/test_class10_science.py):
  - parts lettered A. B. C. like MCQ options A. - D.: a lettered line asking a question ("B. How can ...?") is a part
  - "Attempt either option A or B" ... OR ...: one question per alternative (11, 16, 26, 29, 34, 39)
  - "Attempt either sub-part C or D" ... OR ...: the question stays whole, only its last part is a choice (15, 28, 38)
  - "For visually impaired students" after "- - - -": dropped from the question and its key
  - assertion-reason questions take an option A-D printed once above them
A rule only Class 10 Science needs is defined here and overrides the shared one.
"""
from ....common import *  # noqa: F401,F403
