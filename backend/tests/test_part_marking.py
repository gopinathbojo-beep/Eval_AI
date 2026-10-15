"""A question kept whole with printed part marks is marked part by part, and the parts add up to its marks."""
from app.ocr import prompts
from app.ocr.schemas import EvaluationResult
from app.services.evaluation_rules import apply_part_marks, question_parts, validate_evaluation

Q5 = "Mensuration:\nThe canal...\n(a) Calculate the area. (1.5 marks)\n(b) Find the volume. (1.5 marks)"
Q9 = "Silo: using pi = 22/7: (a) volume (2.5 marks) (b) area (1.5 marks) (c) cost (1 mark)"


def test_parts_found_only_when_their_marks_make_the_question_total():
    assert question_parts(Q5, 3) == [("a", 1.5), ("b", 1.5)]
    assert question_parts(Q9, 5) == [("a", 2.5), ("b", 1.5), ("c", 1.0)]
    assert question_parts(Q9, 6) == []                          # printed parts disagree with the maximum
    assert question_parts("Define x. (2 marks)", 2) == []
    assert question_parts("(a) x (1 mark)\n(b) y", 2) == []     # a part without its own marks


def test_part_marks_are_capped_per_part_and_summed():
    r = EvaluationResult.model_validate({"marks_awarded": 3, "max_marks": 5, "part_marks": [
        {"part": "a", "marks_awarded": 4}, {"part": "9(b)", "marks_awarded": 1.3}, {"part": "c", "marks_awarded": -1}]})
    apply_part_marks(r, question_parts(Q9, 5))
    assert r.part_marks == {"a": 2.5, "b": 1.5, "c": 0.0} and r.marks_awarded == 4.0
    assert validate_evaluation(r, 5).marks_awarded == 4.0


def test_missing_part_falls_back_to_the_total():
    r = EvaluationResult.model_validate({"marks_awarded": 2, "part_marks": {"a": 1.5}})
    apply_part_marks(r, question_parts(Q5, 3))
    assert r.marks_awarded == 2


def test_prompt_lists_parts():
    p = prompts.evaluation_prompt("5", Q5, "key", [], [], [], 3, "5a 40", parts=[("a", 1.5), ("b", 1.5)])
    assert "(a) 1.5, (b) 1.5" in p and '"part_marks"' in p
    assert '"part_marks"' not in prompts.evaluation_prompt("5", Q5, "key", [], [], [], 3, "x")
