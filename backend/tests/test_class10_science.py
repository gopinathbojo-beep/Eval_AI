"""CBSE Class X Science (086) sample paper and marking scheme 2026-27, as InternVL reads the table rows: question
number, the cell's text, the marks column. Through the class 10 Science formatter (class10/subjects/science/) and
its paper design (format.json): 39 questions, 80 marks, either/or questions ("Attempt either option A or B"),
either/or parts ("Attempt either sub-part C or D"), parts A. B. C. beside MCQ options A. - D., and the alternatives
"For visually impaired students" that a sighted student does not answer."""
import re

import pytest

from app.cbse import formatter
from app.cbse.common import choices, standards
from app.cbse.common.keys import segment_answer_keys
from app.cbse.common.paper import parse_question_paper_structure, rows_from_text_layer
from app.ocr.schemas import AnswerKeyItem, AnswerKeyPageResult, QuestionItem, QuestionPageResult

SCIENCE = "class10.subjects.science"
VI = "- - - - - - - - - - - - - -\nFor visually impaired students\n"


def _mcq(stem, *opts):
    return stem + "\n" + "\n".join(f"{l}. {o}" for l, o in zip("ABCD", opts))


AR_INTRO = ("The following two questions consist of two statements – Assertion (A) and Reason (R). Answer these "
            "questions by selecting the appropriate option given below:\nA. Both A and R are true, and R is the correct "
            "explanation of A.\nB. Both A and R are true, and R is not the correct explanation of A.\nC. A is true but R "
            "is false.\nD. A is false but R is true.")

ROWS = [
    (None, "SCIENCE – CODE NO. 086\nSAMPLE QUESTION PAPER*\nCLASS – X (2026-27)\nMax. Marks: 80 Time Allowed: 3 hours"),
    (None, "General Instructions:\n(i) This question paper consists of 39 questions in 3 sections. Section A is Biology, "
           "Section B is Chemistry and Section C is Physics.\n(ii) All questions are compulsory. However, an internal choice "
           "is provided in some questions. A student is expected to attempt only one of the alternatives in these questions."),
    (None, "Section – A"),
    ("1", _mcq("During photosynthesis, what happens to carbon dioxide and water as glucose is formed?",
               "Carbon dioxide gains hydrogen, while water loses electrons.", "Carbon dioxide loses oxygen, while water gains oxygen.",
               "Carbon dioxide is oxidised, while water is reduced.", "Both carbon dioxide and water undergo reduction."), 1),
    ("2", _mcq("Lime water turns cloudy in the presence of a gas, which is a by-product of respiration. Shown below are four "
               "setups kept in sunlight for 24 hours. In which setup is lime water expected to be the cloudiest?", "P", "Q", "R", "S")
     + "\n" + VI + _mcq("Which of the following statement is incorrect concerning the experiment to show that sunlight is "
                        "necessary for photosynthesis?", "The leaf should be destarched before conducting the experiment.",
                        "The leaf kept in darkness will show the presence of starch.",
                        "The leaf exposed to sunlight will show the presence of starch.", "Starch is the end product of photosynthesis."), 1),
    ("3", _mcq("During urine formation, tubular reabsorption and secretion take place in the kidneys. Which of the following "
               "sets correctly indicates both the substances that are reabsorbed in the kidneys?",
               "Glucose and salts", "Glucose and starch", "Glycogen and salts", "Glycogen and starch"), 1),
    ("4", _mcq("In a controlled experiment, the anthers of a mustard plant's flowers were carefully removed in the bud stage "
               "before they matured. The bud was covered with a paper bag.\nWhat will be the most likely result for these flowers?",
               "They will still produce seeds and fruit through self-pollination.",
               "They will attract more insects and produce larger flowers but no fruit.",
               "They will not produce any seeds or fruits.", "They will produce seeds and fruits that are genetically identical to the parent."), 1),
    ("5", _mcq("The Vas deferens and the Oviduct are both targets for surgical contraception (Vasectomy and Tubectomy "
               "respectively). Analysing the process of reproduction, what common biological event is prevented by blocking both these structures?",
               "The production of gametes (sperm and egg).", "The implantation of the fertilized egg into the uterine wall.",
               "The successful meeting and fusion of the male and the female gametes.", "The release of hormones - testosterone and estrogen."), 1),
    ("6", _mcq("The male gamete of an apple plant has seventeen chromosomes. What is the number of chromosomes in the female "
               "gamete and in the cells of the adult plant respectively?", "17,17", "17,34", "34,34", "34,51"), 1),
    ("7", _mcq("A fish living in a pond ecosystem feeds on small aquatic insects (larvae). These insect larvae, in turn, feed "
               "on green algae and small photosynthetic bacteria.\nIn this specific food chain, what is the trophic level classification of fish?",
               "Producer", "Primary Consumer", "Secondary Consumer", "Tertiary Consumer"), 1),
    (None, AR_INTRO),
    ("8", "Assertion (A): The rate of breathing in aquatic organisms is much lower than in the terrestrial organisms.\n"
          "Reason (R): The amount of oxygen dissolved in water is less as compared to the amount of oxygen in air.", 1),
    ("9", "Assertion (A): In an ecosystem, 1% of energy is available for transfer from one trophic level to the next.\n"
          "Reason (R): An average of 10% of the food eaten by organisms is available for flow in the form of chemical energy.", 1),
    ("10", "A. Due to narrowing of the bile duct, the bile secretion from the liver to the small intestine was obstructed. "
           "How will the process of digestion be affected?\nB. How does the length of the intestine depend on the nature of "
           "food habit in different animals?", 2),
    ("11", "Students to attempt either option A or B.\nA. Which parts of the brain perform certain actions for which we do "
           "not have any thinking control? What are such actions called, give two examples.\nOR\nB. How is the information "
           "of touch in the 'sensitive plant' controlled and coordinated?", 2),
    ("12", "What changes are observed in the uterus subsequent to implantation of the young embryo in a human female?", 2),
    ("13", "How do muscles move at the cellular level and respond when processed messages are received from the brain?", 3),
    ("14", "Study the food chain given below:\nPhytoplankton → zooplankton → small fishes → large fish\nA. In the given food "
           "chain, the amount of energy available at the fourth trophic level is 10 kJ, what will be the energy available at "
           "the producer level?\nB. Is it possible to have three more trophic levels in the above food chain? Justify.\n"
           "C. Which of these trophic levels will have the maximum amount of pesticide, if it had washed down in the water "
           "body from agricultural fields. Why?", 3),
    ("15", "In order to study patterns of inheritance, Neha had performed typical Mendelian experiments with pea plants in "
           "the field. In experiment one, she crossed a pea plant having white flowers (vv) with another pea plant bearing "
           "violet flowers (VV). In another experiment she crossed a pea plant having violet flowers and tall height (VVTT) "
           "with another pea plant having white flowers and short height (vvtt).\nWhat percentage is expected for the "
           "following traits as a result of these experiments? Give a reason.\nA. Violet flowers in F1 and F2 generation in "
           "experiment one? (1)\nB. Tall height plants with white flowers in F2 generation in experiment two? (1)\nAttempt "
           "either sub-part C or D.\nC. Percentage of medium height plants with light violet flowers in F1 and F2 generations "
           "in experiment two? Give a reason.\nOR\nD. Percentage of short height plants with white flowers in F1 and F2 "
           "generations in experiment two? (2)", 4),
    ("16", "Attempt either option A or B\nA. Observe the structure of hearts A, B and C shown above and answer the following "
           "questions\nI. Which of the hearts depicted above is present in both birds and Mammals and how are they able to "
           "maintain their body temperature? Give reason for your answer.\nII. Which of the hearts depicted above is present "
           "in fishes, how does circulation of blood take place in them?\nOR\nB.\nI. Observe both the diagrams A and B. Which "
           "diagram indicates inhalation? Describe how it occurs.\nII. If diffusion were to move oxygen in our body, it is "
           "estimated that it would take 3 years for a molecule of oxygen to get to our toes from our lungs. Then, how is "
           "oxygen delivered to all parts of our body?\n" + VI + "A.\nI. How many chambers are present in the hearts of birds "
           "and mammals and how are they able to maintain their body temperature? Give reason for your answer\nII. How many "
           "chambers are present in the heart of fishes, how does circulation of blood take place in them?\nOR\nB.\nI. Describe "
           "the process of inhalation and also mention how are the lungs designed in human beings to maximise the area for "
           "exchange of gases?\nII. If diffusion were to move oxygen in our body, how is oxygen delivered to all parts of our body?", 5),
    (None, "Section – B"),
    ("17", _mcq("Chameleons contain crystals that reflect light and produce colour. Adjusting the spacing between these "
                "crystals, they can alter the wavelengths of light reflected, thus changing their skin colour. Based on the "
                "above information, we can infer that the change in colour by chameleons is a:",
                "chemical change because change in colour takes place.", "chemical change because wavelength of reflected light changes.",
                "physical change because the space between crystals is adjusted.", "physical change because light is reflected by crystals."), 1),
    ("18", _mcq("Rishita summarizes the chlor-alkali process in the following table.\nOption Product Formed Use\nI Hydrogen At "
                "cathode Used as a fuel\nII Chlorine At anode Used to make margarines\nIII Sodium Hydroxide Near cathode To make "
                "soap\nIV Sodium Hydroxide Near anode To make bleaching powder\nIdentify the options that are correctly matched.",
                "I, II and III", "I and III", "II and IV", "I, II, III and IV"), 1),
    ("19", _mcq("Manjeet wants to wash clothes, but the water available is hard. Which of the following inferences is correct?",
                "Ca²⁺ and Mg²⁺ ions react with soap, forming insoluble compounds, whereas detergents do not form such insoluble salts.",
                "Soap is acidic, and detergents are basic.",
                "Soap react with Na+ ions in hard water to form scum while detergents do not react with Na+ ions.",
                "Detergents form lather easily because they are ionic compounds."), 1),
    ("20", _mcq("Which of the following salts contain water of crystallisation:\n(i) Plaster of Paris, (ii) Washing soda,\n"
                "(iii) Baking soda and (iv) Gypsum.", "(i), (ii) and (iii)", "(i), (iii) and (iv)", "(ii), (iii) and (iv)",
                "(i), (ii) and (iv)"), 1),
    ("21", "Which of the following pair of compounds are isomers?\nA.\nB.\nC.\nD.\n" + VI
           + _mcq("The unsaturated hydrocarbon with three carbon atoms is:", "propene", "propane", "pentane", "pentene"), 1),
    ("22", _mcq("A food label is given below. E304 and E307b are added to the flavoured biscuits.\nWhich of the following is "
                "added to food packets for the same reason?", "salt", "vinegar", "nitrogen", "vanilla") + "\n" + VI
           + _mcq("In the food industry nitrogen is used as a/an", "preservative.", "oxidising agent.", "antioxidant.", "colouring agent."), 1),
    ("23", _mcq("Electrical wires made of aluminum", "corrode easily as aluminium is a very reactive metal.",
                "corrode easily because porous flaky aluminium oxide is formed.",
                "do not corrode easily as aluminium oxide forms a protective layer.",
                "do not corrode easily as aluminium is less reactive than metals like sodium, magnesium and zinc."), 1),
    ("24", "Assertion (A): Onion extract loses its smell, when it is added to baking soda solution whereas it retains its "
           "smell when added to lemon juice.\nReason (R): Onion acts as an olfactory indicator.", 1),
    ("25", "Carbon forms millions of compounds whereas silicon, which is just below it in the Periodic Table, forms a few "
           "compounds. Explain the reason for the difference in their ability to form compounds.", 2),
    ("26", "Attempt either option A or B.\nA. An organic compound \"X\" with formula C2H6O is used to blend with petrol.\n"
           "(i) Draw the electron dot structure of \"X\".\n(ii) Write the name and formula of the next homologue of \"X\".\n"
           "(iii) Write the reaction of \"X\" with acetic acid to form a sweet smelling substance.\nOR\nB. Ramya performs an "
           "experiment in the following two steps:\nStep 1: Heats ethanol with conc. H₂SO₄ at 170°C to get product A.\n"
           "Step 2: Passes hydrogen gas over product A, using Ni as a catalyst and gets product B.\n(i) Name the products A "
           "and B.\n(ii) Write the reactions involved in both the steps.\n" + VI + "Attempt either option A or B.\nA. An "
           "organic compound \"X\" with formula C2H6O is used to blend with petrol.\n(i) Name the compound \"X\".\n(ii) Write "
           "the formula of the next homologue of \"X\".\n(iii) Write the reaction of \"X\" with acetic acid.\nOR\nB. Ramya "
           "performs an experiment in the following two steps:\n(i) Name the products A and B.\n(ii) Write the reactions "
           "involved in both the steps.", 3),
    ("27", "Give reason for the following :\nA. A solution of sports electrolyte drink conducts electricity, but coconut oil "
           "does not.\nB. Milkiness disappears when excess of carbon dioxide is passed through lime water.\nC. An iron bridge "
           "near the sea rusts much faster than an iron bridge located in a dry hilly region.", 3),
    ("28", "Aavya and Vihan are studying the properties of metals in school. They use rods of five different metals "
           "aluminium, silver, copper, iron and zinc attached to a central point. (Study the graph)\nA. On the basis of the "
           "graph obtained, which metal is the best conductor of heat?\nB. Gold is a better conductor of heat than aluminium "
           "but it is not as good as copper. The time taken for the candle to drop if one of the rods were made of gold would "
           "have been:\n(i) 15 s\n(ii) 20 s\n(iii) 35 s\n(iv) 10 s\nAttempt either sub-part C or D.\nC. The length of all the "
           "metal rods is increased by 20% without any change in the thickness. Will the time required for the candles to "
           "drop be affected? How and why?\nOR\nD. Mayank tries the experiment with an apparatus similar to figure (1). The "
           "thickness of rods is not the same in his apparatus. Will the inference he draws be correct? Justify your answer.\n"
           + VI + "Aavya and Vihan use rods of equal length and thickness made of five different metals – A, B, C, D and E.\n"
           "A. On the basis of the experimental result, which metal is the best conductor of heat?\nB. Metal G is a better "
           "conductor of heat than metal A but it is not as good as metal C. The time taken would have been:\n(i) 15 s\n"
           "(ii) 20 s\n(iii) 35 s\n(iv) 10 s\nAttempt either sub-part C or D.\nC. The length of all the metal rods is "
           "increased by 20%. Will the time required for the sensor to beep be affected?\nOR\nD. Mayank keeps the length of "
           "all the rods the same, but the thickness of rods is not the same. Will the inference be correct?", 4),
    ("29", "Attempt either option A or B.\nA.\nI. Refer to the dialogue between Alisha, Drishti and Bhushan in the chemistry "
           "lab. Who all do you agree with and why?\nII. Assess the following chemical equations. Identify the error(s) and "
           "rewrite the equation after correction.\n(i) MgCl2 + AgNO3 → AgCl2 + MgNO3\n(ii) Al + H2SO4 → Al2SO4 + H2O\nOR\nB.\n"
           "I. Refer to the dialogue between Daljeet and Avik in the chemistry lab. Who has understood decomposition "
           "reactions correctly? Justify your answer.\nII. Analyse the observations given in following two cases. Are these "
           "observations correct?\n(i) Iron fillings are added to an aqueous solution of magnesium sulphate.\n(ii) Aluminium "
           "metal is added to dilute sulphuric acid", 5),
    (None, "Section – C"),
    ("30", _mcq("A student wants to determine the focal length of a convex lens using sunlight. Which of the following "
                "practical procedures will give the most accurate result?", "Move the lens close to a wall and measure the blurred circle.",
                "Hold the lens above a sheet of paper and adjust until the smallest, brightest spot is formed.",
                "Measure the thickness of the lens with a scale.", "Look through the lens at a distant object."), 1),
    ("31", _mcq("An electrical appliance rated 1000 W is operated at 250 V. What current does it draw?",
                "0.25 A", "2.5 A", "4.0 A", "10 A"), 1),
    ("32", "Assertion (A): The apparent depth of a coin in water is less than its real depth.\nReason (R): Light bends away "
           "from the normal when it travels from water to air.", 1),
    ("33", "A. State Snell's Law of refraction.\nB. Define the refractive index of a material with respect to another "
           "material giving the mathematical expression.", 2),
    ("34", "Attempt either option A or B.\nA.\nI. State Joule's Law of heating.\nII. What happens to the heat produced in a "
           "conductor if the resistance is doubled while keeping other variables constant?\nOr\nB.\nI. Define resistivity.\n"
           "II. Justify with an example why resistivity is an intrinsic property of a material.", 2),
    ("35", "A concave lens forms an image that is 1/3rd the size of the object, as shown in the diagram. If the object is "
           "placed 24 cm in front of the lens, determine:\nA. the type of lens.\nB. the image distance\nC. the focal length "
           "of the lens\n" + VI + "A student places an object 24 cm from a convex lens of focal length 12 cm. Calculate the "
           "image position and determine whether the image is real or virtual.", 3),
    ("36", "A. State the Right-Hand Thumb Rule and describe how it helps determine the direction of magnetic field around a "
           "current-carrying conductor.\nB. Explain how the magnetic field changes with distance from the conductor.", 3),
    ("37", "The figure shows a circuit with a 15 V battery connected to several resistors. Using the given circuit diagram:\n"
           "A. Find the total current supplied by the battery.\nB. Calculate the potential difference between points A and B.\n"
           + VI + "A 15 V battery is connected in series with three resistors of 2 Ω, 3 Ω, and 5 Ω. Calculate:\nA. The total "
           "resistance in the circuit.\nB. The total current supplied by the battery.\nC. The voltage drop across the 3Ω resistor.", 3),
    ("38", "A school has installed an automatic electromagnetic door-locking system at the main entrance.\nA. Why is an iron "
           "core kept inside the solenoid in this locking mechanism?\nB. How can we determine the magnetic poles in this "
           "solenoid?\nAttempt either subpart (C) or (D).\nC. If the current in the solenoid is increased from 1 A to 2 A, "
           "explain how the magnetic effect changes and its effect on unlocking the door.\nOR\nD. If the source of the current "
           "is fixed, how can we increase the magnetic field in the solenoid?\n" + VI + "A student places a small magnetic "
           "compass on a wooden table.\nA. What causes the compass needle to deflect when current flows through the wire?\n"
           "B. What happens to the compass needle when the current in the wire is switched off?\nC. Explain how the amount of "
           "current in the wire affects the magnitude of deflection of the compass needle?\nOR\nD. When the direction of "
           "current is reversed, the compass deflects in the opposite direction. Explain how the Right-Hand Thumb Rule "
           "accounts for this change.", 4),
    ("39", "Attempt either option A or B.\nA.\nI. What is meant by accommodation of the human eye?\nII. What is the near "
           "point of a normal eye and what does it signify?\nIII. Name which type of lens is used to correct the defect in "
           "which a person cannot see distant objects clearly.\nIV. Draw a diagram to show how the choice of your lens helps "
           "to see distant objects clearly?\nOR\nB.\nI. What is dispersion of light?\nII. Which colour of light deviates the "
           "least during dispersion through a prism?\nIII. State why the sky appears dark to an astronaut in outer space.\n"
           "IV. Draw a simple labelled diagram to show how white light splits into different colours while passing through "
           "a glass prism.\n" + VI + "A.\nI. What is meant by hypermetropia (long-sightedness)?\nII. What is the far point of "
           "a normal human eye and what does it signify?\nIII. Name the type of lens used to correct hypermetropia.\nIV. "
           "Explain why a hypermetropic eye is unable to focus nearby objects on the retina.\nOR\nB.\nI. Why does Earth's "
           "atmosphere exhibit Tyndall's effect?\nII. Which colour of light has the shortest wavelength?\nIII. Why do "
           "danger/stop signs use red colour?\nIV. State why the sky appears blue even though sunlight is white.", 5),
]


def _paper():
    items = [QuestionItem(raw_question_number=r[0], question_text=r[1], marks=r[2] if len(r) > 2 else None) for r in ROWS]
    return [({"page_number": 1}, QuestionPageResult(page_number=1, questions=items))]


@pytest.fixture(scope="module")
def doc():
    with formatter.use(SCIENCE):
        return parse_question_paper_structure(_paper())


def _by(doc):
    return {q.normalized_number: q for q in doc.questions}


def test_matches_the_class10_science_design(doc):
    assert standards.check(doc, standards.load("10", "Science")) == []
    assert doc.exam_max_marks == 80 and choices.max_total(doc.questions) == 80
    assert all(q.verification_status == "UNVERIFIED" for q in doc.questions)


def test_sections_biology_chemistry_physics(doc):
    by = _by(doc)
    assert {by[n].section for n in ("1", "15", "16(a)")} == {"Section – A"}
    assert {by[n].section for n in ("17", "29(b)")} == {"Section – B"}
    assert {by[n].section for n in ("30", "39(a)")} == {"Section – C"}


def test_either_option_a_or_b_splits_the_question(doc):
    by = _by(doc)
    for n in ("11", "16", "26", "29", "34", "39"):
        assert sorted(q.normalized_number for q in doc.questions if q.choice_group == n) == [f"{n}(a)", f"{n}(b)"]
    assert by["34(b)"].question_text.startswith("B.") and "resistivity" in by["34(b)"].question_text


def test_either_sub_part_c_or_d_keeps_the_question_whole(doc):
    by = _by(doc)
    for n in ("15", "28", "38"):
        assert n in by and by[n].choice_group is None and by[n].max_marks == 4
        assert re.search(r"\bC\.\s", by[n].question_text) and re.search(r"\bD\.\s", by[n].question_text)
        assert by[n].question_type != "mcq"


def test_visually_impaired_alternative_is_not_part_of_the_question(doc):
    by = _by(doc)
    assert "visually" not in by["2"].question_text.casefold() and "destarched" not in by["2"].question_text
    assert "hypermetropia" not in by["39(b)"].question_text and "Tyndall" not in by["39(b)"].question_text
    assert "2 Ω, 3 Ω, and 5 Ω" not in by["37"].question_text


def test_types(doc):
    by = _by(doc)
    assert {by[n].question_type for n in ("1", "2", "8", "9", "17", "24", "31", "32")} == {"mcq"}
    assert by["10"].question_type != "mcq" and by["14"].question_type != "mcq"


KEY_ROWS = [
    ("1", "A. Carbon dioxide gains hydrogen, while water loses electrons.", 1),
    ("2", "C. R\nFor visually impaired students\nB. The leaf kept in darkness will show the presence of starch", 1),
    *[(str(n), a, 1) for n, a in ((3, "A. Glucose and salts"), (4, "C. They will not produce any seeds or fruits."),
                                  (5, "C. The successful meeting and fusion of the male and female gametes"),
                                  (6, "B. 17, 34"), (7, "C. Secondary Consumer"), (8, "D. A is false but R is true."),
                                  (9, "D. A is false but R is true"))],
    ("10", "The Bile juice from the liver makes the food alkaline for the pancreatic enzymes to act. (0.5+0.5)\n"
           "Herbivores eating grass need a longer small intestine to allow the cellulose to be digested. (1)", 2),
    ("11", "The actions on which we do not have any thinking control are controlled by the mid-brain and hind-brain. "
           "These are called involuntary actions.\nOR\nThe information of touch is communicated by electrical-chemical "
           "means from cell to cell.", 2),
    ("15", "A. In experiment one, in F1 all plants (100%) will have violet (Vv) flowers. (1)\nB. 3/16 or 18.75% pea plants "
           "will have tall height and white flowers. (1)\nAttempt sub - part C or D.\nC. No half way characteristics are "
           "produced (zero percent). (2)\nOR\nD. In F2 generation 1/16 or 6.25 % plants will have short height with white "
           "flowers. (2)", 4),
    ("16", "Student to attempt either option A or B.\nA.\nI. C – Four chambered heart. (1)\nII. A – Two chambered heart. (1)\n"
           "OR\nB.\nI. A depicts inhalation. (1)\nII. The respiratory pigment haemoglobin has a very high affinity for "
           "oxygen. (2)\nFor visually impaired students\nI. Four chambers are present. (1)\nII. Two chambered heart. (1)\n"
           "OR\nI. Ribs get lifted (0.5)\nII. In human beings, the respiratory pigment haemoglobin. (2)", 5),
]


def test_key_follows_the_paper(doc):
    keys = [AnswerKeyItem(question_number=n, answer_text=t, marks=m) for n, t, m in KEY_ROWS]
    with formatter.use(SCIENCE):
        segmented = segment_answer_keys([({"page_number": 1}, AnswerKeyPageResult(page_number=1, answers=keys))], doc.questions)
    by = {k.normalized_number: k for k in segmented}
    assert "leaf kept in darkness" not in by["2"].answer_text
    assert "mid-brain" in by["11(a)"].answer_text and "sensitive" not in by["11(a)"].answer_text
    assert "electrical-chemical" in by["11(b)"].answer_text
    assert "\nD." in by["15"].answer_text  # one key for the question; C or D both in it
    assert "haemoglobin" in by["16(b)"].answer_text and "Four chambers are present" not in by["16(b)"].answer_text
    assert "Four chambered" in by["16(a)"].answer_text



# The PDF's text layer as it prints the table rows (number, the question's lines, the marks cell), and what InternVL
# returned for the same pages of the uploaded sample paper: number cells dropped, rows run together, Q36 skipped
FOOTER = "*There is no change in the Question Paper Design and Assessment Pattern for Academic Session 2026-27."


def _filler(first, last):
    return "".join(f"{n} Which of the following is true for case {n}? 1\nA. P\nB. Q\nC. R\nD. S\n" for n in range(first, last + 1))


TEXT_LAYER = [
    "SCIENCE – CODE NO. 086\nMax. Marks: 80 Time Allowed: 3 hours\nSection – A\n"
    "1 During photosynthesis, what happens to carbon dioxide and water as glucose is 1\nformed?\n"
    "A. Carbon dioxide gains hydrogen.\nB. Carbon dioxide loses oxygen.\nC. Carbon dioxide is oxidised.\n"
    "D. Both undergo reduction.\n"
    "2 During urine formation, tubular reabsorption and secretion take place in the 1\nkidneys. Which of the "
    "following sets are reabsorbed?\nA. Glucose and salts\nB. Glucose and starch\nC. Glycogen and salts\n"
    "D. Glycogen and starch\n"
    "The following two questions consist of two statements – Assertion (A) and Reason (R).\n"
    "A. Both A and R are true.\nB. A is true but R is false.\n" + FOOTER,
    "3 Assertion (A): The rate of breathing in aquatic organisms is much lower. 1\n"
    "Reason (R): Less oxygen is dissolved in water.\n" + _filler(4, 29)
    + "Section – C\nA student wants to determine the focal length of a convex lens using sunlight. 1\n30\n"
    "Which of the following practical procedures will give the most accurate result?\n" + _filler(31, 34)
    + "35 3\nA concave lens forms an image that is 1/3rd the size of the object. Determine:\nA. the type of lens.\n"
    "36 A. State the Right-Hand Thumb Rule. 3\n"
    "B. Explain how the magnetic field changes with distance from the conductor.\n" + FOOTER,
    "37 3\nThe figure shows a circuit with a 15 V battery.\nA. Find the total current supplied by the battery.\n"
    "- - - - - - - - - - - - - -\nFor visually impaired students\nA 15 V battery is connected in series.\n" + FOOTER,
]
INTERNVL = [
    [(None, "SCIENCE - CODE NO. 086\nMax. Marks: 80", None), ("1", "During photosynthesis, what happens ...", 1),
     (None, "During urine formation, tubular reabsorption and secretion take place ...", 1)],
    [("3", "Assertion (A): The rate of breathing ...", 1), (None, "Which of the following practical procedures ...", 1),
     ("35", "A concave lens forms an image ...", 3)],
    [(None, "The figure shows a circuit with a 15 V battery.", None)],
]


def test_digital_paper_takes_its_rows_from_the_text_layer():
    pages = [({"page_number": i + 1, "page_text": t},
              QuestionPageResult(page_number=i + 1, questions=[QuestionItem(raw_question_number=n, question_text=x, marks=m)
                                                               for n, x, m in blocks]))
             for i, (t, blocks) in enumerate(zip(TEXT_LAYER, INTERNVL))]
    doc = parse_question_paper_structure(pages)
    by = _by(doc)
    assert [q.normalized_number for q in doc.questions] == [str(n) for n in range(1, 38)]
    assert [by[n].max_marks for n in ("1", "2", "3", "30", "35", "36", "37")] == [1, 1, 1, 1, 3, 3, 3]
    assert by["2"].question_text.startswith("During urine formation") and "Assertion" not in by["2"].question_text
    assert by["30"].question_text.startswith("A student wants to determine")  # its number cell sits below its first line
    assert by["35"].question_text.startswith("A concave lens") and by["36"].question_text.startswith("A. State the Right")
    assert "visually" not in by["37"].question_text and "2026-27" not in by["37"].question_text
    assert by["1"].section == "Section – A" and by["30"].section == "Section – C"


def test_scanned_paper_keeps_the_model_blocks():
    pages = [({"page_number": 1}, QuestionPageResult(page_number=1, questions=[QuestionItem(raw_question_number="1",
                                                                                            question_text="What is a cell?")]))]
    assert rows_from_text_layer(pages) is pages
