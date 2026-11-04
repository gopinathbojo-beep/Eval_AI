from types import SimpleNamespace as NS

import pytest

from app.cbse.variant import adopt_printed_profile


def legacy_exam(grade=12, subject="Mathematics"):
    return NS(standard_profile_id=None, standard_options={}, standard_version=None,
              school_class=NS(name=f"{grade}-C"), subject=NS(name=subject, code=None),
              standard_validation={"old": True})


def test_printed_sample_paper_adopts_whole_question_extraction():
    exam = legacy_exam()
    pages = [{"page_text": "SUBJECT: MATHEMATICS (041) SAMPLE QUESTION PAPER CLASS- XII (2026-27)"}]
    assert adopt_printed_profile(exam, pages) == "cbse-12-041"
    assert exam.standard_options == {"accessibility": "standard"}
    assert exam.standard_validation is None
    assert adopt_printed_profile(exam, pages) is None


@pytest.mark.parametrize("text", [
    "School exam with 38 questions and 80 marks",
    "SUBJECT: MATHEMATICS (041) SAMPLE QUESTION PAPER CLASS- X",
    "SUBJECT: PHYSICS (042) SAMPLE QUESTION PAPER CLASS- XII",
    "SUBJECT: MATHEMATICS SAMPLE QUESTION PAPER CLASS- XII",
    "",
])
def test_unconfirmed_or_mismatched_papers_keep_their_existing_mode(text):
    exam = legacy_exam()
    assert adopt_printed_profile(exam, [{"page_text": text}]) is None
    assert exam.standard_profile_id is None


def test_other_supported_subjects_are_recognised_from_their_source():
    exam = legacy_exam(10, "Science")
    assert adopt_printed_profile(exam, [{"page_text":
        "SCIENCE (086) SAMPLE QUESTION PAPER CLASS X"}]) == "cbse-10-086"
