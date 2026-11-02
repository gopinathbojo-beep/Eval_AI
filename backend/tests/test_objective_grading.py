"""MCQs are marked against the key's option (objective.py), never by the grading model: the correct letter, or the
correct option's value, is full marks; another option is 0; a letter and a value naming different options, or a value
that is no option, goes to the teacher. The answers are the ones on a Class 10 Maths Basic sheet the model had marked
0 or 0.5 for "no calculation shown"."""
import pytest

from app.cbse.common.objective import grade

Q13 = "A ladder 15 m long reaches a window 12 m above the ground. The distance of the foot of the ladder from the base " \
      "of the wall is\n(A) 8 m                       (B) 9 m              (C) 10 m            (D) 13 m"
K13 = "Answer: (B)\n(Hypotenuse )² =(Base)² + (Perpendicular)² ⇒ (15)² = (Base)² +(12)²\n⇒ Base = 9 m\n(B) 9m"
Q14 = "The value of sin²60° − 2 tan² 45° − cos²30° is\n(A) −2                          (B) −1                 (C) 1"
K14 = "Answer: (A)\nsin 2/((A) −2)60° 2tan²45° cos²30° = (√3/2) – 2(1)² – (√3/2)"
Q12 = "Mean and median of certain data are 32 and 30 respectively. Using empirical formula, the value of mode is\n" \
      "(A) 36                         (B) 26                (C) 30               (D) 20"
K12 = "Answer: (B)\nMode = 3Median – 2Mean ⇒ Mode= 3×30 - 2×32 ⇒ Mode = 26\n(B) 26"
Q3 = "For what value of p does the pair of Linear equations 4x+ py+ 8 = 0 and 2x+2y+ 2 = 0 has a unique solution\n" \
     "(A) p= 4 only       (B) p= 2 only         (C) p≠4            (D)p≠2"
K3 = "Answer: (C)\nFor unique solution a₁/a ≠ b₁/b ⇒4/2 ≠ p/2 ⇒ p≠ 4\n(C) p≠ 4"
Q5 = "If one root of the quadratic equation ax² + bx+ c= 0 is the reciprocal of the other, then\n" \
     "(A) b= c                 (B) a= b          (C) ac= 1        (D) a= c"
K5 = "Answer: (D)\nLet the roots be α and 1/α\n(D) a= c"
Q19 = "ASSERTION (A): The probability of getting number 8 on rolling a die is zero (0) REASON (R): The probability of an " \
      "impossible event is zero (0)"
K19 = "Answer: (A)\nP(getting 8 on rolling a die) = 0/8\n(A)Both Assertion (A)and Reason (R)are true"


@pytest.mark.parametrize("q, key, written, marks", [
    (Q13, K13, "13> B", 1),           # the letter
    (Q13, K13, "13> B. 9 m", 1),      # the letter and its option
    (Q13, K13, "13> 9m", 1),          # the option's value alone
    (Q14, K14, "14> -2", 1),          # "−2" printed with a minus sign
    (Q3, K3, "3> C. p+4", 1),         # the right letter; "p≠4" misread
    (Q19, K19, "19> A", 1),           # assertion-reason: no options in the question, the key's letter decides
    (Q13, K13, "13> C", 0),           # another letter
    (Q13, K13, "13> 10 m", 0),        # another option's value
])
def test_an_mcq_is_marked_by_the_option_chosen(q, key, written, marks):
    res = grade("mcq", q, key, written, 1)
    assert res.marks_awarded == marks and res.confidence == 1.0


@pytest.mark.parametrize("q, key, written", [
    (Q12, K12, "12> A. 26"),          # letter (A) but 26 is option (B)
    (Q5, K5, "5> a/c"),               # matches no printed option
])
def test_a_choice_that_cannot_be_read_one_way_goes_to_the_teacher(q, key, written):
    res = grade("mcq", q, key, written, 1)
    assert res.marks_awarded == 0 and res.confidence < 0.5 and res.feedback.startswith("Check the sheet")


def test_a_written_answer_is_left_to_the_grading_model():
    assert grade("short_answer", Q13, K13, "Base = 9 m", 2) is None
    assert grade("mcq", Q13, "Base² = 15² - 12²", "13> B", 1) is None  # the key names no option
