from types import SimpleNamespace as NS

from app.formatter.accountancy import segment_answers


def _q(n):
    return NS(id=f"q{n}", normalized_number=str(n), display_number=str(n), question_text=f"Question {n}",
              max_marks=3.0, structure=None)


def _block(label, number, text, conf, norm=None):
    return NS(raw_question_label=label, question_number=number, normalized_question_label=norm or number,
              question_number_confidence=conf, answer_text=text, bbox=None, ocr_confidence=0.5)


def _page(n, *blocks):
    return {"page_number": n}, NS(answers=list(blocks))


def _by_number(out):
    return {a.normalized_number: a.answer_text for a in out}


QS = [_q(n) for n in (18, 19, 20, 21, 22, 23, 24)]


def test_a_bare_heading_and_part_labels_start_the_next_question_not_the_last_one():
    # page 5 ends Q19 and the student writes "23" with nothing under it yet; page 6 goes on with "a)" of Q23
    pages = [
        _page(4, _block("19,", "Q19", "19, Purchased assets for 6,30,000", 0.95)),
        _page(5, _block("Q19", "Q19", "ii) Crane Ltd. A/c Dr. 630000", 0.6),
              _block("23", "Q23", "", None)),
        _page(6, _block("a)", "Q23", "a) Bank A/c Dr 67500", 0.9, "Q23(a)"),
              _block("b)", "Q23", "b) Bank A/c Dr 96000", 0.9, "Q23(b)")),
    ]
    got = _by_number(segment_answers(pages, QS))
    assert "Bank" not in got["19"] and "Crane" in got["19"]
    assert "67500" in got["23"] and "96000" in got["23"]


def test_part_labels_of_the_current_question_stay_with_it():
    pages = [
        _page(4, _block("19.", "Q19", "19. Debentures to issue = 7000", 0.95),
              _block("ii)", "Q19", "ii) Journal: Assets A/c Dr", 0.9, "Q19(ii)")),
        # a part label the model put under an earlier question never pulls the answer back
        _page(5, _block("20.", "Q20", "20. Average profit", 0.95),
              _block("b)", "Q19", "b) goodwill = 3 x average", 0.9, "Q19(b)")),
    ]
    got = _by_number(segment_answers(pages, QS))
    assert "Journal" in got["19"] and "goodwill" in got["20"] and "goodwill" not in got["19"]


def test_a_number_read_with_low_confidence_is_not_trusted_on_its_own():
    pages = [_page(4, _block("19.", "Q19", "19. Debentures", 0.95),
                   _block("2?", "Q24", "", 0.2))]                   # a smudge read as a number, nothing under it
    assert set(_by_number(segment_answers(pages, QS))) == {"19"}
