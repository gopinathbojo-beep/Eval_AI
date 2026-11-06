"""Pages of another student's paper inside an answer sheet are left out (another subject or class) or flagged
(another roll number); pages without a header are kept."""
from types import SimpleNamespace as NS

from app.ocr.schemas import StudentPageResult
from app.services.sheet_pages import check_pages, class_number

EXAM = NS(subject=NS(name="Science"), school_class=NS(name="10-C"))


def _page(n, header=None):
    return ({"page_number": n}, StudentPageResult(page_number=n, page_header=header))


def test_class_numbers():
    assert [class_number(x) for x in ("10-C", "Class 12", "XII-A", "X C", "x", "IX", "", None, "C")] == \
        [10, 12, 12, 10, 10, 9, None, None, None]


def test_other_subject_or_class_page_is_left_out():
    results = [_page(1, {"roll_number": "12A-34", "subject": "Maths", "class_name": "XII-A"}),
               _page(2, {"roll_number": "10C22", "subject": "Science", "class_name": "X-C"}),
               _page(3), _page(4, {"subject": "Mathematics"})]
    excluded, notes, other = check_pages(results, EXAM)
    assert excluded == {1, 4} and [n["page"] for n in notes] == [1, 4] and other == []
    assert "subject Maths" in notes[0]["reason"] and "class XII-A" in notes[0]["reason"]


def test_same_paper_other_roll_is_flagged_and_misreads_are_not():
    results = [_page(1, {"roll_number": "10C22", "subject": "Science"}), _page(2, {"roll_number": "1OC22"}),
               _page(3, {"roll_number": "10C22"}), _page(4, {"roll_number": "10C07", "subject": "Science"})]
    excluded, _, other = check_pages(results, EXAM)
    assert excluded == set() and other == [{"page": 4, "roll_number": "10C07"}]


def test_unknown_subject_or_no_header_keeps_the_page():
    excluded, _, _ = check_pages([_page(1, {"subject": "Unit test"}), _page(2)], EXAM)
    assert excluded == set()


def test_class_one_year_off_is_a_slip_not_another_paper():
    """A Class 12 student writing "XI" in the class box: the page stays (it holds Q1-6)."""
    exam = NS(subject=NS(name="Accountancy"), school_class=NS(name="12-C"))
    excluded, _, _ = check_pages([_page(1, {"roll_number": "12B06", "subject": "Accountancy", "class_name": "XI lily"}),
                                  _page(2, {"class_name": "X-A"})], exam)
    assert excluded == {2}  # Class 10 in a Class 12 exam is another paper; XI is not


def test_roll_misreads_match_the_class_list_spelling():
    from app.services.student_identity import _look_alike
    assert _look_alike("12806") == _look_alike("12B06") and _look_alike("128-01") == _look_alike("12B-01")
    assert _look_alike("12B05") != _look_alike("12B02")  # a different digit is a different student
