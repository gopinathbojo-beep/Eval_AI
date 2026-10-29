"""The exam's subject picks the paper format: Tamil rules never touch an English paper; English papers parse the same
under any non-Tamil subject; a Tamil paper keeps its rules."""
import threading

from app.ocr.schemas import AnswerKeyItem, AnswerKeyPageResult, QuestionItem, QuestionPageResult
from app.services import job_queue, paper_format
from app.formatter.common import choices
from app.formatter.common.paper import parse_question_paper_structure
from app.formatter.common.keys import segment_answer_keys
from app.formatter.common.numbering import normalize_question_number


def _q(label, text, marks=None):
    return QuestionItem(raw_question_number=label, question_text=text, marks=marks)


def _parse(*items):
    return parse_question_paper_structure([({"page_number": 1}, QuestionPageResult(page_number=1, questions=list(items)))])


def test_subject_picks_the_format():
    assert paper_format.for_subject("Tamil") == paper_format.TAMIL
    assert paper_format.for_subject("Tamil II") == paper_format.TAMIL
    assert paper_format.for_subject("தமிழ்") == paper_format.TAMIL
    assert paper_format.for_subject("English") == paper_format.ENGLISH
    assert paper_format.for_subject("Science") == paper_format.ENGLISH
    assert paper_format.for_subject(None) is None


def test_tamil_labels_are_plain_text_under_an_english_subject():
    assert normalize_question_number("1(அ)") == "1(a)"                         # no subject: the script decides
    with paper_format.use(paper_format.TAMIL):
        assert normalize_question_number("1(அ)") == "1(a)"
    with paper_format.use(paper_format.ENGLISH):
        assert normalize_question_number("1(அ)") is None
        assert normalize_question_number("1(a)") == "1(a)"
    assert paper_format.active() is None                                        # restored after the block


def test_tamil_either_or_word_is_no_choice_in_an_english_paper():
    text = "(a) Translate: நான் பள்ளிக்குச் செல்கிறேன்\nஅல்லது\n(b) Translate: அவள் பாடுகிறாள்"
    with paper_format.use(paper_format.TAMIL):
        assert len(choices.split_alternatives(text)) == 2
    with paper_format.use(paper_format.ENGLISH):
        assert len(choices.split_alternatives(text)) == 1


def test_english_paper_parses_the_same_under_every_format():
    items = [_q(None, "Maximum Marks : 7"), _q("1", "Define a pronoun.", 2),
             _q("2", "Write a letter to your friend.\nOR\nWrite a diary entry.", 5)]
    want = [("1", 2), ("2(a)", 5), ("2(b)", 5)]
    for fmt in (None, paper_format.ENGLISH, paper_format.TAMIL):
        with paper_format.use(fmt):
            assert [(q.display_number, q.max_marks) for q in _parse(*items).questions] == want


def test_queued_job_runs_with_its_exam_format(monkeypatch):
    seen = []
    monkeypatch.setattr(job_queue, "engine_for", lambda exam_id, reads_pages=True: "internvl")
    monkeypatch.setattr(job_queue, "format_for", lambda exam_id: paper_format.ENGLISH)
    monkeypatch.setattr(job_queue, "switch_engine", lambda engine: None)
    job_queue.submit("exam-1", lambda: seen.append(paper_format.active()))
    job_queue.wait_idle(5)
    assert seen == [paper_format.ENGLISH] and paper_format.active() is None


def test_request_format_does_not_leak_into_other_threads():
    with paper_format.use(paper_format.ENGLISH):
        out = []
        t = threading.Thread(target=lambda: out.append(paper_format.active()))
        t.start()
        t.join()
    assert out == [None]


# English formats found while checking every English layout


def test_attempt_any_is_a_rule_not_a_question():
    doc = _parse(_q(None, "SECTION C"), _q(None, "Attempt any two of the following."),
                 *[_q(str(n), f"Describe character {n} in detail.", 5) for n in range(7, 10)])
    assert [q.display_number for q in doc.questions] == ["7", "8", "9"]
    assert {q.answer_any for q in doc.questions} == {2} and choices.max_total(doc.questions) == 10


def test_passage_in_the_same_block_as_its_instruction_is_kept():
    passage = "The sun rose slowly over the hills. Farmers walked to their fields while children ran to school."
    doc = _parse(_q(None, f"Read the passage given below and answer the questions that follow.\n{passage}"),
                 _q("1", "Where did the farmers go?", 1))
    assert doc.questions[0].question_text.startswith("[Reading Passage Context]\nThe sun rose")


def test_each_parts_own_mark_adds_up():
    doc = _parse(_q("3", "Read and answer.\n(a) Identify the subject. (1 mark)\n(b) Identify the predicate. (1 mark)"))
    assert [(q.display_number, q.max_marks) for q in doc.questions] == [("3", 2)]
    doc = _parse(_q("4", "(a) Write a letter. (5 marks)\nOR\n(b) Write a notice. (5 marks)"))
    assert [(q.display_number, q.max_marks) for q in doc.questions] == [("4(a)", 5), ("4(b)", 5)]


def test_key_for_a_question_whose_parts_are_separate_questions_is_split():
    from types import SimpleNamespace
    exam = [SimpleNamespace(display_number=n, normalized_number=n, choice_group=None, max_marks=1) for n in ("3(a)", "3(b)")]
    page = AnswerKeyPageResult(page_number=1, answers=[AnswerKeyItem(question_number="3", answer_text="(a) The boy\n(b) runs fast")])
    keys = segment_answer_keys([({"page_number": 1}, page)], exam)
    assert [(k.normalized_number, k.answer_text, k.marks) for k in keys] == [("3(a)", "(a) The boy", 1), ("3(b)", "(b) runs fast", 1)]
