"""Maths answers are graded step by step against the marking scheme (common/steps.py): the scheme's marks are added up
by the backend, an OR choice inside a question counts its better alternative once, a step with results is decided by
them alone (never by the model), the question's own numbers prove nothing, and any step the model judged sends the
question to the teacher. The answers are from a Class 10 Maths Basic sheet the whole-answer grader misjudged."""
from app.cbse.common.steps import grade

Q36_TEXT = ("An Art and craft teacher prepared a fan ... (i) The angle subtended at the centre of the sector is 60⁰. "
            "(iii)(B) If 29.6 cm of designer tape is required ...")
Q36 = {"question_text": Q36_TEXT, "points": [
    {"marks": 1.0, "text": "(i) Required area of one face of the fan = 60/360 ×22/7 × 10² = 1100/21"},
    {"marks": 1.0, "text": "= 60/360 ×22/7 (10² −4²) = 44 cm²"},
    {"marks": 1.0, "alt_group": 1, "alt": "A", "text": "(iii) (A) boundary length of black sheet region on one face"},
    {"marks": 1.0, "alt_group": 1, "alt": "A", "text": "=12 + 44/3 = 80/3 cm"},
    {"marks": 0.5, "alt_group": 1, "alt": "B", "text": "(iii) (B) 2(10 – 4) + θ/360 × 2 ×22/7 (10 + 4) = 29.6"},
    {"marks": 1.0, "alt_group": 1, "alt": "B", "text": "θ/360 × 88  = 17.6"},
    {"marks": 0.5, "alt_group": 1, "alt": "B", "text": "θ = (17.6×360)/88 = 72°"},
]}
ANSWER_36 = ("outer radius = 10 cm\ninner radius = 4 cm\ncentral angle = 60°\ni) area of sector: A = (θ/360) × πr²\n"
             "= (60/360) × (22/7) × 10²\n= (1/6) × (22/7) × 100\n= 1100/21 cm²\nii) A = (θ/360) × π(R² − r²)\n"
             "= (1/6) × (22/7) × (10² − 4²)\n= (1/6) × (22/7) × 84\n= 44 cm²")


def yes_to_everything(system, prompt, schema):
    student = prompt.split("STUDENT ANSWER (OCR of handwriting)\n", 1)[1].split("\n\nDoes", 1)[0]
    return schema(present=True, quote=student.splitlines()[0])


def test_an_or_choice_not_attempted_costs_nothing_and_earns_nothing():
    res = grade(Q36, ANSWER_36, 4, yes_to_everything)
    # (i) and (ii) earned by their values; (iii)(A) needs 80/3, (iii)(B) 29.6 / 17.6 / 72: none written, whatever the
    # model says; (iii)(A)'s wording step is the model's call, so the question goes to the teacher
    assert res.marks_awarded in (2, 3) and res.confidence == 0.5
    assert not any("29.6" in m or "17.6" in m for m in res.matched_points)


def test_every_step_written_is_full_marks_without_the_model():
    q21 = {"question_text": "A. Find the smallest number which when increased by 17 is exactly divisible by both 520 "
                            "and 468.",
           "points": [{"marks": 1.0, "text": "520 = 2³ x 5 x 13; 468 = 2² x 3² x 13"},
                      {"marks": 0.5, "text": "LCM = 2³ x 3² x 5 x 13 = 4680"},
                      {"marks": 0.5, "text": "∴ The required number is (4680 – 17). i.e., 4663"}]}
    answer = "520 = 2³ × 5 × 13\n468 = 2² × 3² × 13\nLCM = 2³ × 3² × 5 × 13\n= 4680\nx + 17 = 4680\nx = 4680 - 17\n= 4663"
    res = grade(q21, answer, 2, None)
    assert res.marks_awarded == 2 and res.confidence == 1.0


def test_the_questions_own_numbers_prove_no_step():
    q35 = {"question_text": "Twelve minutes later, the angle of depression of the ambulance is found to be 60°.",
           "points": [{"marks": 1.0, "text": "⇒ h/√3 + 12x = h√3 ⇒ h = 6√3x ∴ BC = 6 x"},
                      {"marks": 4.0, "text": "∴ Total time taken = (6+12) minutes = 18 minutes"}]}
    res = grade(q35, "time interval = 12 min.\ntan 30° = h/x", 5, None)
    assert res.marks_awarded == 0  # "12" is the question's twelve minutes, not the student's working


def test_equal_values_count_whatever_their_form():
    q25 = {"question_text": "Points A (3,1), B (5, 1), C (a, b) and D (4, 3) are vertices of a parallelogram ABCD.",
           "points": [{"marks": 2.0, "text": "⇒ (3+a)/2 = 9/2 and (1+b)/2 = 4/2"}]}
    assert grade(q25, "(3+a)/2 = 9/2\n(1+b)/2 = 2", 2, None).marks_awarded == 2  # 4/2 is 2
    q28 = {"question_text": "Determine the ratio in which the point (– 6, y) divides ...",
           "points": [{"marks": 1.0, "text": "k = 3/2, i.e., Required ratio is 3:2"}]}
    assert grade(q28, "m : n = 3 : 2", 1, None).marks_awarded == 1  # the ratio 3:2 is 3/2


def test_a_scheme_that_does_not_add_up_keeps_the_whole_answer_grading():
    assert grade({"points": [{"marks": 1.0, "text": "a"}]}, "a", 2, None) is None
