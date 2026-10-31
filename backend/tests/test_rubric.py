"""Marking rubrics built from answer keys (app/formatter/common/rubric.py), on lines from the papers in exam/."""
from app.cbse.common.rubric import build_rubric


def kinds(r):
    return [(p.marks, p.kind, p.part, p.expected) for p in r.points]


def test_cbse_key_points_with_parts_units_numbers():
    q = "(a) Define atmospheric pressure and state its SI unit.\n(b) Explain why sharp cutting edge tools exert higher pressure."
    key = ("o (a) Atmospheric Pressure: The force per unit area ...\nSI Unit: Pascal (Pa) or Newton per square meter (N/m²).\n"
           "o (b) Pressure is inversely proportional to area (P=F/A).\n• Marking Scheme:")
    crit = ["1 Mark: Correct definition of atmospheric pressure + SI unit (Pa or N/m²).",
            "1 Mark: Explaining inverse relation between area and pressure (P∝1/A)."]
    r = build_rubric(q, key, crit, 2.0)
    assert kinds(r) == [(1, "unit", "a", ["Pa", "N/m²"]), (1, "meaning", "b", [])] and not r.problems


def test_exact_words_find_their_part_and_deductions_are_kept_apart():
    key = "o \n(a) since \no \n(b) otherwise \n"
    r = build_rubric("Fill in the blanks:\n(a) He has been living in Delhi ___ 2018.\n(b) Work hard ___ you will not pass.",
                     key, ["1 Mark: Correct preposition choice (since).", "1 Mark: Correct conjunction choice (otherwise).",
                           "(Deduct ½ mark for major grammatical errors)."], 2.0)
    assert kinds(r) == [(1, "exact", "a", ["since"]), (1, "exact", "b", ["otherwise"])]
    assert r.deductions == ["Deduct ½ mark for major grammatical errors"]


def test_marks_per_item_expand_over_a_table():
    key = "| Line | Incorrect Word | Correct Word |\n|------|------|------|\n|(a)   | habits | habit |\n|(b)   | Help | helps |"
    r = build_rubric("Identify the error in each line.", key, ["1 Mark per correct identification and correction pair."], 2.0)
    assert kinds(r) == [(1, "exact", "a", ["habit"]), (1, "exact", "b", ["helps"])]


def test_combined_point_splits_and_parts_follow_paper_order():
    q = "(a) What is rusting of iron? Write its equation. (2 marks)\n(b) Why does copper turn green? (2 marks)\n(c) List two methods. (1 mark)"
    key = ("o (a) Rusting: iron reacting with oxygen and water.\nChemical Equation: 4Fe + 3O₂ + xH₂O →2Fe₂O₃ ⋅xH₂O\n"
           "o (b) Copper forms basic copper carbonate.\nChemical Equation: 2Cu + H₂O + CO₂ + O₂ → Cu(OH)₂ + CuCO₃\n"
           "o (c) Painting, galvanization.")
    crit = ["2 Marks: Definition of rusting (1 mark) + balanced chemical formula/equation (1 mark).",
            "2 Marks: Explanation of basic copper carbonate formation (1 mark) + chemical equation (1 mark).",
            "1 Mark: Two valid prevention methods (½ mark each)."]
    r = build_rubric(q, key, crit, 5.0)
    assert [(p.marks, p.kind, p.part) for p in r.points] == [(1, "meaning", "a"), (1, "equation", "a"), (1, "meaning", "b"),
                                                             (1, "equation", "b"), (1, "meaning", "c")]
    assert r.points[1].expected == ["4Fe + 3O₂ + xH₂O →2Fe₂O₃ ⋅xH₂O"] and not r.problems


def test_set_key_layout_with_final_values():
    key = ("Q5. Sum of k(k + 1) (5 Marks)\nMODEL ANSWER\nFor n = 10:\n10 × 11 × 12 / 3 = 440\nKEYWORD MARKING SCHEME\n"
           "Marks Awarded for\n1.0 Splitting k(k + 1) = k² + k.\n1.0 Using the formulas for Σk² and Σk.\n"
           "1.5 Correct simplification to n(n + 1)(n + 2)/3.\n1.5 Correct evaluation for n = 10: 440.\nFINAL STRUCTURE\nSet 7 Mathematics 5 15")
    r = build_rubric("Find the sum of (1 × 2) + (2 × 3) + … + n(n + 1) for n = 10.", key, [], None)
    assert [p.marks for p in r.points] == [1, 1, 1.5, 1.5] and r.points[-1].kind == "number"
    assert r.points[-1].expected == ["440"] and r.stated_total == 5 and not r.problems


def test_writing_task_keeps_its_bands_and_problems_are_reported():
    crit = ["1 Mark: Format (Date, Time, Salutation, Signature/Name).", "2 Marks: Content (Expressing joy ...).",
            "2 Marks: Expression (Coherence, vocabulary, correct grammar)."]
    r = build_rubric("Imagine you are Connie. Write a diary entry expressing your happiness.", "Sample Answer: ...", crit, 5.0)
    assert r.kind == "open" and [(p.marks, p.kind) for p in r.points] == [(1, "criterion"), (2, "criterion"), (2, "criterion")]
    short = build_rubric("Write a diary entry.", "", crit[:2], 5.0)
    assert short.problems == ["Marking points add up to 3, the question has 5 marks"]
    part = build_rubric("(a) Calculate the area. (1.5 marks)\n(b) Calculate the volume. (1.5 marks)", "",
                        ["1 Mark: Formula substitution and calculation for area (40 m²) (a).",
                         "2 Marks: Multiplying area by length to get volume (10,000 m³) (b)."], 3.0)
    assert part.problems == ["Part (a) has 1.5 marks in the paper but 1 in the key",
                             "Part (b) has 1.5 marks in the paper but 2 in the key"]


def test_rubric_is_stored_with_the_key_and_reconfirmed_only_when_it_changes():
    from types import SimpleNamespace as NS
    from app.services.mapping_service import refresh_rubric
    q = NS(question_text="Define calorific value and state its SI unit.", max_marks=2.0)
    key = NS(answer_text="Definition: heat on complete combustion of 1 kg of fuel.\nSI Unit: Kilojoule per kilogram (kJ/kg).",
             criteria=["1 Mark: Correct definition specifying complete combustion of 1 kg fuel.", "1 Mark: Correct SI unit (kJ/kg)."],
             rubric=None, rubric_status="UNREVIEWED")
    refresh_rubric(key, q)
    assert [(p["marks"], p["kind"], p["expected"]) for p in key.rubric["points"]] == [(1, "meaning", []), (1, "unit", ["kJ/kg"])]
    key.rubric_status = "CONFIRMED"  # the teacher verified the key
    refresh_rubric(key, q)
    assert key.rubric_status == "CONFIRMED"  # same rubric: still confirmed
    key.criteria = key.criteria[:1]
    refresh_rubric(key, q)
    assert key.rubric_status == "UNREVIEWED" and key.rubric["problems"] == ["Marking points add up to 1, the question has 2 marks"]


def test_key_without_a_marking_scheme_is_one_point_for_the_whole_question():
    r = build_rubric("Who wrote Thirukkural?", "Answer: Thiruvalluvar", [], 1.0)
    assert [(p.marks, p.kind, p.expected) for p in r.points] == [(1, "exact", ["Thiruvalluvar"])] and not r.problems
    r = build_rubric("Explain photosynthesis.", "Plants make food from carbon dioxide and water using sunlight.", [], 3.0)
    assert [(p.marks, p.kind) for p in r.points] == [(3, "meaning")] and not r.problems


def test_grader_gets_the_rubric_points():
    from types import SimpleNamespace as NS
    from app.services.evaluation_service import rubric_criteria
    r = build_rubric("Fill in:\n(a) ___ 2018.\n(b) Work hard ___.", "o \n(a) since \no \n(b) otherwise",
                     ["1 Mark: Correct preposition choice (since).", "1 Mark: Correct conjunction choice (otherwise).",
                      "(Deduct ½ mark for major grammatical errors)."], 2.0)
    key = NS(rubric=r.to_dict(), criteria=["raw line"])
    assert rubric_criteria(key) == ["[1 mark] (a) exact answer: since - Correct preposition choice (since).",
                                    "[1 mark] (b) exact answer: otherwise - Correct conjunction choice (otherwise).",
                                    "[deduction] Deduct ½ mark for major grammatical errors"]
    assert rubric_criteria(NS(rubric=None, criteria=["raw line"])) == ["raw line"]
