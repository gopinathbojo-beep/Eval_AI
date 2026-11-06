"""Answer coverage: what a student must answer, and a missing answer's number found inside another answer."""
from types import SimpleNamespace as N

from app.services.coverage import _label_line, units


def q(num, pos, choice=None, any_n=None, compulsory=True, section="A"):
    return N(id=f"q{num}", display_number=num, normalized_number=num, position=pos, choice_group=choice,
             answer_any=any_n, compulsory=compulsory, section=section)


def test_units_count_either_or_once_and_answer_any_n_times():
    qs = [q("1", 1), q("2", 2), q("11A", 3, choice="11"), q("11B", 4, choice="11"),
          q("20", 5, any_n=2, compulsory=False, section="C"), q("21", 6, any_n=2, compulsory=False, section="C"),
          q("22", 7, any_n=2, compulsory=False, section="C")]
    us = units(qs)
    assert [u["label"] for u in us] == ["Q1", "Q2", "Q11A or Q11B", "any 2 of Q20-Q22"]
    assert sum(u["need"] for u in us) == 5


def test_a_missing_number_is_found_where_a_student_writes_it():
    p = _label_line("12")
    assert all(p.match(x) for x in ("12> (d) capital reserve", "12) ...", "Q12. ans", "12, Purchased", "12 (b) x"))
    assert not any(p.match(x) for x in ("120000 To Bank", "1,20,000", "₹ 12,000", "12000"))
