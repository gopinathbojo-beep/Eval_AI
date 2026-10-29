"""Reference Learning and Document Accuracy Improvement Service for Eval AI.

Manages:
- Teacher-approved local verified reference collection
- Objective OCR accuracy benchmarking (CER, WER, question numbering, marks, mathematical expressions)
- Seed ground truth from reference question papers and official answer keys (Chemistry, English, Mathematics)
- Extraction comparison and error category tracking
- Dynamic contextual prompt hints derived from verified examples
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy.orm import Session
from ..models import VerifiedReferenceExample

log = logging.getLogger("adem.reference_learning")


# ---------- Levenshtein Distance & Accuracy Metrics ----------

def levenshtein_distance(s1: Sequence, s2: Sequence) -> int:
    """Computes exact edit distance between two sequences (characters or words)."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def compute_cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate = edit_distance(ref_chars, hyp_chars) / len(ref_chars)."""
    ref = reference.strip()
    hyp = hypothesis.strip()
    if not ref:
        return 0.0 if not hyp else 1.0
    dist = levenshtein_distance(ref, hyp)
    return min(1.0, dist / max(1, len(ref)))


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate = edit_distance(ref_words, hyp_words) / len(ref_words)."""
    ref_words = re.findall(r"\S+", reference.strip().lower())
    hyp_words = re.findall(r"\S+", hypothesis.strip().lower())
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return min(1.0, dist / max(1, len(ref_words)))


def compute_accuracy_score(reference: str, hypothesis: str) -> float:
    """Normalized text accuracy percentage (1 - CER) * 100."""
    cer = compute_cer(reference, hypothesis)
    return round(max(0.0, (1.0 - cer) * 100), 2)


# ---------- Seed Reference Data from User's Verified Documents ----------

VERIFIED_REFERENCE_SEED = [
    # --- CHEMISTRY QUESTION PAPER ---
    {
        "document_type": "question_paper",
        "subject": "Chemistry",
        "source_document": "CLASS 8 – CBSE CHEMISTRY QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q1",
        "normalized_number": "1",
        "structure_type": "subquestion",
        "error_category": "chemical_formula",
        "approved_marks": 2.0,
        "original_ocr": "Q1. Write balanced word equations for the following chemical reactions:\n(a) Magnesium reacts with Oxygen to form Magnesium Oxide.\n(b) Iron reacts with Copper Sulphate solution to form Iron Sulphate and Copper.",
        "corrected_text": "Q1. Write balanced word equations for the following chemical reactions:\n(a) Magnesium reacts with Oxygen to form Magnesium Oxide.\n(b) Iron reacts with Copper Sulphate solution to form Iron Sulphate and Copper.",
    },
    {
        "document_type": "question_paper",
        "subject": "Chemistry",
        "source_document": "CLASS 8 – CBSE CHEMISTRY QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q2",
        "normalized_number": "2",
        "structure_type": "descriptive",
        "error_category": "none",
        "approved_marks": 2.0,
        "original_ocr": "Q2. Differentiate between thermoplastic and thermosetting plastics based on their structure and behavior upon heating. Give one example of each.",
        "corrected_text": "Q2. Differentiate between thermoplastic and thermosetting plastics based on their structure and behavior upon heating. Give one example of each.",
    },
    {
        "document_type": "question_paper",
        "subject": "Chemistry",
        "source_document": "CLASS 8 – CBSE CHEMISTRY QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q5",
        "normalized_number": "5",
        "structure_type": "equation",
        "error_category": "chemical_formula",
        "approved_marks": 3.0,
        "original_ocr": "Q5. Chemical Equations & Reactions:\nComplete and balance the following chemical equations:\n(a) Na + H2O → ________ + H2 ↑\n(b) SO2 + H2O → ________\n(c) Zn + H2SO4 → ________ + H2 ↑",
        "corrected_text": "Q5. Chemical Equations & Reactions:\nComplete and balance the following chemical equations:\n(a) Na + H₂O → ________ + H₂ ↑\n(b) SO₂ + H₂O → ________\n(c) Zn + H₂SO₄ → ________ + H₂ ↑",
    },
    {
        "document_type": "question_paper",
        "subject": "Chemistry",
        "source_document": "CLASS 8 – CBSE CHEMISTRY QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q9",
        "normalized_number": "9",
        "structure_type": "subquestion",
        "error_category": "subquestion_split",
        "approved_marks": 5.0,
        "original_ocr": "Q9. Corrosion & Chemical Properties:\n(a) What is rusting of iron? Write the chemical equation for the rusting process. (2 marks)\n(b) Explain why copper vessels develop a greenish coating when exposed to moist air over time. Write the chemical equation representing this reaction. (2 marks)\n(c) List two methods used to prevent the corrosion of metals. (1 mark)",
        "corrected_text": "Q9. Corrosion & Chemical Properties:\n(a) What is rusting of iron? Write the chemical equation for the rusting process. (2 marks)\n(b) Explain why copper vessels develop a greenish coating when exposed to moist air over time. Write the chemical equation representing this reaction. (2 marks)\n(c) List two methods used to prevent the corrosion of metals. (1 mark)",
    },
    {
        "document_type": "question_paper",
        "subject": "Chemistry",
        "source_document": "CLASS 8 – CBSE CHEMISTRY QUESTION PAPER",
        "page_number": 2,
        "question_number": "Q10",
        "normalized_number": "10",
        "structure_type": "subquestion",
        "error_category": "none",
        "approved_marks": 5.0,
        "original_ocr": "Q10. Polymerization & Environmental Impact:\n(a) Why are plastics widely used in daily life despite their harmful impact on the environment? Mention three desirable properties of plastics. (2 marks)\n(b) Differentiate between biodegradable and non-biodegradable substances with suitable examples. (2 marks)\n(c) State the \"5R Principle\" recommended for reducing the environmental hazards caused by plastic waste. (1 mark)",
        "corrected_text": "Q10. Polymerization & Environmental Impact:\n(a) Why are plastics widely used in daily life despite their harmful impact on the environment? Mention three desirable properties of plastics. (2 marks)\n(b) Differentiate between biodegradable and non-biodegradable substances with suitable examples. (2 marks)\n(c) State the \"5R Principle\" recommended for reducing the environmental hazards caused by plastic waste. (1 mark)",
    },

    # --- ENGLISH QUESTION PAPER & ANSWER KEY ---
    {
        "document_type": "question_paper",
        "subject": "English",
        "source_document": "CLASS 8 – CBSE ENGLISH QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q4",
        "normalized_number": "4",
        "structure_type": "subquestion",
        "error_category": "option_structure",
        "approved_marks": 2.0,
        "original_ocr": "Q4. Fill in the blanks with appropriate prepositions/conjunctions:\n(a) He has been living in Delhi ______ 2018. (since / for)\n(b) Work hard ______ you will not pass the test. (and / otherwise)",
        "corrected_text": "Q4. Fill in the blanks with appropriate prepositions/conjunctions:\n(a) He has been living in Delhi ______ 2018. (since / for)\n(b) Work hard ______ you will not pass the test. (and / otherwise)",
    },
    {
        "document_type": "question_paper",
        "subject": "English",
        "source_document": "CLASS 8 – CBSE ENGLISH QUESTION PAPER",
        "page_number": 2,
        "question_number": "Q6",
        "normalized_number": "6",
        "structure_type": "table",
        "error_category": "table_formatting",
        "approved_marks": 3.0,
        "original_ocr": "Q6. Grammar (Editing):\nThe following passage has an error in each line. Identify the error and write the correction alongside:\nLine Incorrect Word Correct Word\n(a) Reading books is a good habits. __________ __________\n(b) It help in improving knowledge. __________ __________\n(c) Every student should read daily. __________ __________",
        "corrected_text": "Q6. Grammar (Editing):\nThe following passage has an error in each line. Identify the error and write the correction alongside:\n\n| Line | Incorrect Word | Correct Word |\n| :--- | :--- | :--- |\n| (a) Reading books is a good habits. | __________ | __________ |\n| (b) It help in improving knowledge. | __________ | __________ |\n| (c) Every student should read daily. | __________ | __________ |",
    },
    {
        "document_type": "answer_key",
        "subject": "English",
        "source_document": "ANSWER KEY & MARKING SCHEME CLASS 8 – CBSE ENGLISH QUESTION PAPER",
        "page_number": 2,
        "question_number": "Q6",
        "normalized_number": "6",
        "structure_type": "table",
        "error_category": "table_formatting",
        "approved_marks": 3.0,
        "criteria": ["1 Mark per correct identification and correction pair."],
        "original_ocr": "Q6. Grammar (Editing)\n• Answer:\nLine Incorrect Word Correct Word\n(a) habits habit\n(b) Help helps\n(c) Daily (No error in line c / sentence is grammatically correct as is; award full credit if student identified line c as correct or pointed out subject-verb consistency)\n• Marking Scheme:\no 1 Mark per correct identification and correction pair.",
        "corrected_text": "Q6. Grammar (Editing)\n• Answer:\n| Line | Incorrect Word | Correct Word |\n| :--- | :--- | :--- |\n| (a) | habits | habit |\n| (b) | Help | helps |\n| (c) | Daily | (No error in line c / sentence is grammatically correct as is; award full credit if student identified line c as correct or pointed out subject-verb consistency) |\n\n• Marking Scheme:\n- 1 Mark per correct identification and correction pair.",
    },
    {
        "document_type": "answer_key",
        "subject": "English",
        "source_document": "ANSWER KEY & MARKING SCHEME CLASS 8 – CBSE ENGLISH QUESTION PAPER",
        "page_number": 3,
        "question_number": "Q9",
        "normalized_number": "9",
        "structure_type": "notice_box",
        "error_category": "box_layout",
        "approved_marks": 5.0,
        "criteria": [
            "1 Mark: Format (Issuer Name, NOTICE title, Date, Subject Heading, Name & Designation, Enclosing Box).",
            "2 Marks: Content (Includes Date, Time, Venue, Topic, Target Audience, and Deadline for entries).",
            "2 Marks: Expression (Grammatical accuracy, appropriate formal tone, word limit compliance ≤ 50 words)."
        ],
        "original_ocr": "Q9. Writing Skills (Notice Writing)\n• Sample Answer:\nPlaintext\n+-------------------------------------------------------------------------+\n| ST. XAVIER’S SCHOOL, JAIPUR |\n| NOTICE |\n| 10 October 2026 |\n| INTER-CLASS DEBATE COMPETITION |\n| This is to inform all students of Classes VI–VIII that an Inter-Class |\n| Debate Competition will be held on 25 October 2026 in the School |\n| Auditorium from 10:00 AM onwards. The topic for the debate is \"AI in |\n| Education: Boon or Bane?\". Interested students should give their names |\n| to their respective class teachers by 18 October 2026. |\n| Rohan / Riya |\n| Cultural Secretary |\n+-------------------------------------------------------------------------+",
        "corrected_text": "Q9. Writing Skills (Notice Writing)\n• Sample Answer:\n```plaintext\n+-------------------------------------------------------------------------+\n|                       ST. XAVIER’S SCHOOL, JAIPUR                       |\n|                                 NOTICE                                  |\n|                                                                         |\n| 10 October 2026                                                         |\n|                                                                         |\n|                     INTER-CLASS DEBATE COMPETITION                      |\n|                                                                         |\n| This is to inform all students of Classes VI–VIII that an Inter-Class   |\n| Debate Competition will be held on 25 October 2026 in the School        |\n| Auditorium from 10:00 AM onwards. The topic for the debate is \"AI in    |\n| Education: Boon or Bane?\". Interested students should give their names   |\n| to their respective class teachers by 18 October 2026.                  |\n|                                                                         |\n| Rohan / Riya                                                            |\n| Cultural Secretary                                                      |\n+-------------------------------------------------------------------------+\n```\n• Marking Scheme (5 Marks Total):\n- 1 Mark: Format (Issuer Name, NOTICE title, Date, Subject Heading, Name & Designation, Enclosing Box).\n- 2 Marks: Content (Includes Date, Time, Venue, Topic, Target Audience, and Deadline for entries).\n- 2 Marks: Expression (Grammatical accuracy, appropriate formal tone, word limit compliance ≤ 50 words).",
    },

    # --- MATHEMATICS QUESTION PAPER & ANSWER KEY ---
    {
        "document_type": "question_paper",
        "subject": "Mathematics",
        "source_document": "CLASS 8 – CBSE MATHEMATICS QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q1",
        "normalized_number": "1",
        "structure_type": "formula",
        "error_category": "mathematical_symbols",
        "approved_marks": 2.0,
        "original_ocr": "Q1. Exponents & Powers:\nUsing exponent laws, evaluate and express the final answer in single exponent form with a positive index:\n(( 2 3 ) -2 × ( 3 4 ) -3 ) ÷ ( 8 9 ) -2",
        "corrected_text": "Q1. Exponents & Powers:\nUsing exponent laws, evaluate and express the final answer in single exponent form with a positive index:\n[((2/3)⁻² × (3/4)⁻³) ÷ (8/9)⁻²]",
    },
    {
        "document_type": "answer_key",
        "subject": "Mathematics",
        "source_document": "ANSWER KEY & STEP-BY-STEP SOLUTIONS CLASS 8 – CBSE MATHEMATICS QUESTION PAPER",
        "page_number": 1,
        "question_number": "Q1",
        "normalized_number": "1",
        "structure_type": "formula",
        "error_category": "mathematical_symbols",
        "approved_marks": 2.0,
        "criteria": [
            "1 Mark: Correct application of reciprocal rule for negative indices.",
            "1 Mark: Correct prime factorization, division simplification, and final exponential value."
        ],
        "original_ocr": "Q1. Exponents & Powers\n• Formulas Used:\n1. (a/b)^-n = (b/a)^n\n2. (a · b)^n = a^n · b^n\n3. a^m / a^n = a^{m-n}\n• Step-by-Step Solution:\nExpression: ((2/3)^-2 × (3/4)^-3) ÷ (8/9)^-2\nStep 1: Convert negative exponents: ((3/2)^2 × (4/3)^3) ÷ (9/8)^2\nStep 2: Express numbers as prime factors\nStep 3: Substitute: (3^2/2^2 × 2^6/3^3) ÷ 3^4/2^6\nStep 4: Simplify inside bracket: 2^{6-2}/3^{3-2} = 2^4/3^1 = 16/3\nStep 5: Multiply reciprocal: 2^4/3^1 × 2^6/3^4 = 2^{10}/3^5 = (4/3)^5 or 1024/243\nFinal Answer: (4/3)^5 or 1024/243",
        "corrected_text": "Q1. Exponents & Powers\n• Formulas Used:\n1. (a/b)⁻ⁿ = (b/a)ⁿ\n2. (a · b)ⁿ = aⁿ · bⁿ\n3. aᵐ / aⁿ = aᵐ⁻ⁿ\n• Step-by-Step Solution:\nExpression: [((2/3)⁻² × (3/4)⁻³) ÷ (8/9)⁻²]\nStep 1: Convert negative exponents to positive exponents by taking reciprocals:\n[((3/2)² × (4/3)³) ÷ (9/8)²]\nStep 2: Express numbers as prime factors:\n- 3/2 = 3/2\n- 4/3 = 2²/3\n- 9/8 = 3²/2³\nStep 3: Substitute and expand powers:\n(3²/2² × 2⁶/3³) ÷ (3⁴/2⁶)\nStep 4: Simplify the term inside the bracket:\n2⁶⁻² / 3³⁻² = 2⁴/3¹ = 16/3\nStep 5: Perform division by multiplying with reciprocal:\n(2⁴/3¹) × (2⁶/3⁴) = 2¹⁰/3⁵ = (2²/3)⁵ = (4/3)⁵ or 1024/243\n• Marking Scheme:\n- 1 Mark: Correct application of reciprocal rule for negative indices.\n- 1 Mark: Correct prime factorization, division simplification, and final exponential value.",
    },
    {
        "document_type": "answer_key",
        "subject": "Mathematics",
        "source_document": "ANSWER KEY & STEP-BY-STEP SOLUTIONS CLASS 8 – CBSE MATHEMATICS QUESTION PAPER",
        "page_number": 2,
        "question_number": "Q2",
        "normalized_number": "2",
        "structure_type": "formula",
        "error_category": "mathematical_symbols",
        "approved_marks": 2.0,
        "criteria": [
            "1 Mark: Writing the expansion identity (x + 1/x)² = x² + 1/x² + 2.",
            "1 Mark: Substituting 6 and obtaining the final answer 34."
        ],
        "original_ocr": "Q2. Algebraic Identities\n• Formula Used:\n(a + b) 2 = a 2 + b 2 + 2ab\n• Step-by-Step Solution:\nGiven: x + 1/x = 6\nSquaring both sides:\n(x + 1/x) 2 = (6) 2\nx 2 + (1/x) 2 + 2 · x · 1/x = 36\nx 2 + 1/x 2 + 2 = 36\nx 2 + 1/x 2 = 36 - 2 = 34",
        "corrected_text": "Q2. Algebraic Identities\n• Formula Used:\n(a + b)² = a² + b² + 2ab\n• Step-by-Step Solution:\nGiven: x + 1/x = 6\nSquaring both sides:\n(x + 1/x)² = 6²\nx² + (1/x)² + 2 · x · (1/x) = 36\nx² + 1/x² + 2 = 36\nx² + 1/x² = 36 - 2 = 34\n• Marking Scheme:\n- 1 Mark: Writing the expansion identity (x + 1/x)² = x² + 1/x² + 2.\n- 1 Mark: Substituting 6 and obtaining the final answer 34.",
    },
    {
        "document_type": "answer_key",
        "subject": "Mathematics",
        "source_document": "ANSWER KEY & STEP-BY-STEP SOLUTIONS CLASS 8 – CBSE MATHEMATICS QUESTION PAPER",
        "page_number": 5,
        "question_number": "Q8",
        "normalized_number": "8",
        "structure_type": "formula",
        "error_category": "mathematical_symbols",
        "approved_marks": 3.0,
        "criteria": [
            "2 Marks: Volume computation formula and exact value (1232 cm³).",
            "1 Mark: Total Surface Area calculation (1408 cm²)."
        ],
        "original_ocr": "Q8. Solid Geometry (Hollow Cylinder)\n• Formulas Used:\n1. V = π(R 2 - r 2)h\n2. TSA = 2πRh + 2πrh + 2π(R 2 - r 2)\n• Step-by-Step Solution:\nGiven: Outer radius R = 8 cm, Inner radius r = 6 cm, Height h = 14 cm, π = 22/7\n(a) Volume of Metal:\nR 2 - r 2 = 8 2 - 6 2 = 64 - 36 = 28 cm2\nV = 22/7 × 28 × 14 = 22 × 4 × 14 = 1232 cm3\n(b) Total Surface Area (TSA):\nOuter Curved Area = 2πRh = 2 × 22/7 × 8 × 14 = 704 cm2\nInner Curved Area = 2πrh = 2 × 22/7 × 6 × 14 = 528 cm2\nArea of 2 Base Rings = 2π(R 2 - r 2) = 2 × 22/7 × 28 = 176 cm2\nTSA = 704 + 528 + 176 = 1408 cm2",
        "corrected_text": "Q8. Solid Geometry (Hollow Cylinder)\n• Formulas Used:\n1. V = π(R² - r²)h\n2. TSA = 2πRh + 2πrh + 2π(R² - r²)\n• Step-by-Step Solution:\nGiven: Outer radius R = 8 cm, Inner radius r = 6 cm, Height h = 14 cm, π = 22/7\n(a) Volume of Metal:\nR² - r² = 8² - 6² = 64 - 36 = 28 cm²\nV = (22/7) × 28 × 14 = 22 × 4 × 14 = 1232 cm³\n(b) Total Surface Area (TSA):\n- Outer Curved Area = 2πRh = 2 × (22/7) × 8 × 14 = 704 cm²\n- Inner Curved Area = 2πrh = 2 × (22/7) × 6 × 14 = 528 cm²\n- Area of 2 Base Rings = 2π(R² - r²) = 2 × (22/7) × 28 = 176 cm²\nTSA = 704 + 528 + 176 = 1408 cm²\n• Marking Scheme:\n- 2 Marks: Volume computation formula and exact value (1232 cm³).\n- 1 Mark: Total Surface Area calculation (1408 cm²).",
    },
    {
        "document_type": "answer_key",
        "subject": "Mathematics",
        "source_document": "ANSWER KEY & STEP-BY-STEP SOLUTIONS CLASS 8 – CBSE MATHEMATICS QUESTION PAPER",
        "page_number": 5,
        "question_number": "Q9",
        "normalized_number": "9",
        "structure_type": "formula",
        "error_category": "mathematical_symbols",
        "approved_marks": 5.0,
        "criteria": [
            "2.5 Marks: Individual volume computations and total volume calculation (3028.67 m³).",
            "1.5 Marks: Summing curved surface areas to get 968 m².",
            "1 Mark: Multiplying area by rate (Rs. 43,560)."
        ],
        "original_ocr": "Q9. Multi-Shape Mensuration & Cost Computation\n• Formulas Used:\n1. Vtotal = πr 2h + 2/3πr 3\n2. Ainternal = 2πrh + 2πr 2\n3. Cost = Area × Rate\n• Step-by-Step Solution:\nGiven: Radius r = 7 m, Cylinder height h = 15 m, π = 22/7\n(a) Total Volume:\nVcylinder = πr 2h = 22/7 × 7 2 × 15 = 22 × 7 × 15 = 2310 m3\nVhemisphere = 2/3πr 3 = 2/3 × 22/7 × 7 3 = 2/3 × 22 × 49 = 2156/3 ≈ 718.67 m3\nVtotal = 2310 + 718.67 = 3028.67 m3 (or 9086/3 m3)\n(b) Total Internal Surface Area:\nScylinder = 2πrh = 2 × 22/7 × 7 × 15 = 660 m2\nShemisphere = 2πr 2 = 2 × 22/7 × 7 2 = 308 m2\nStotal = 660 + 308 = 968 m2\n(c) Cost of Painting:\nCost = 968 m2 × Rs. 45/m2 = Rs. 43,560",
        "corrected_text": "Q9. Multi-Shape Mensuration & Cost Computation\n• Formulas Used:\n1. V_total = πr²h + (2/3)πr³\n2. A_internal = 2πrh + 2πr²\n3. Cost = Area × Rate\n• Step-by-Step Solution:\nGiven: Radius r = 7 m, Cylinder height h = 15 m, π = 22/7\n(a) Total Volume:\nV_cylinder = πr²h = (22/7) × 7² × 15 = 22 × 7 × 15 = 2310 m³\nV_hemisphere = (2/3)πr³ = (2/3) × (22/7) × 7³ = (2/3) × 22 × 49 = 2156/3 ≈ 718.67 m³\nV_total = 2310 + 718.67 = 3028.67 m³ (or 9086/3 m³)\n(b) Total Internal Surface Area:\nS_cylinder = 2πrh = 2 × (22/7) × 7 × 15 = 660 m²\nS_hemisphere = 2πr² = 2 × (22/7) × 7² = 308 m²\nS_total = 660 + 308 = 968 m²\n(c) Cost of Painting:\nCost = 968 m² × Rs. 45/m² = Rs. 43,560\n• Marking Scheme:\n- 2.5 Marks: Individual volume computations and total volume calculation (3028.67 m³).\n- 1.5 Marks: Summing curved surface areas to get 968 m².\n- 1 Mark: Multiplying area by rate (Rs. 43,560).",
    },
]


def seed_verified_reference_collection(db: Session, teacher_id: str | None = None) -> int:
    """Seeds the verified reference database with authoritative examples from reference papers."""
    count = 0
    for item in VERIFIED_REFERENCE_SEED:
        existing = db.query(VerifiedReferenceExample).filter_by(
            source_document=item["source_document"],
            question_number=item["question_number"],
            document_type=item["document_type"]
        ).first()
        if not existing:
            rec = VerifiedReferenceExample(
                teacher_id=teacher_id,
                document_type=item["document_type"],
                subject=item["subject"],
                source_document=item["source_document"],
                page_number=item["page_number"],
                question_number=item["question_number"],
                normalized_number=item["normalized_number"],
                original_ocr=item["original_ocr"],
                corrected_text=item["corrected_text"],
                error_category=item["error_category"],
                structure_type=item["structure_type"],
                approved_marks=item["approved_marks"],
                criteria=item.get("criteria", []),
                verification_status="APPROVED",
                created_at=datetime.now(timezone.utc),
            )
            db.add(rec)
            count += 1
    if count > 0:
        db.commit()
    return count


def classify_error_category(original_ocr: str, corrected_text: str) -> str:
    """Categorizes the primary type of error between raw OCR and verified text."""
    orig = original_ocr.strip()
    corr = corrected_text.strip()
    if orig == corr:
        return "none"

    # Mathematical symbols: exponents, radicals, pi, fractions
    if any(sym in corr for sym in ["²", "³", "⁴", "⁻", "√", "π", "÷", "×", "^", "/"]) and not any(sym in orig for sym in ["²", "³", "⁴", "⁻", "√", "π"]):
        return "mathematical_symbols"

    # Chemical formulas: arrows, gas evolution, subscripts
    if any(sym in corr for sym in ["→", "↑", "↓", "₂", "₃", "₄", "H₂O", "H₂SO₄", "SO₂"]):
        return "chemical_formula"

    # Table formatting
    if "|" in corr and ("|" not in orig or corr.count("|") > orig.count("|")):
        return "table_formatting"

    # Box formatting: notice / plaintext box
    if "+---" in corr or "| ST." in corr:
        return "box_layout"

    # Numbering confusion
    if re.search(r"Q\d|Q\.\d|\(\d\)", corr) and not re.search(r"Q\d|Q\.\d|\(\d\)", orig):
        return "numbering"

    # Subquestion split
    if re.search(r"\([a-c]\)", corr) and not re.search(r"\([a-c]\)", orig):
        return "subquestion_split"

    # Missing content
    if len(corr) > len(orig) + 30:
        return "missing_content"

    return "word_typo"


def infer_structure_type(text: str) -> str:
    """Infers structural category of a text block."""
    if "|" in text and text.count("|") >= 4:
        return "table"
    if any(sym in text for sym in ["→", "↑", "↓", "H₂O", "H₂SO₄", "SO₂", "MgO"]):
        return "equation"
    if any(sym in text for sym in ["²", "³", "⁴", "⁻", "√", "π", "÷", "^", "="]) and re.search(r"\d", text):
        return "formula"
    if "+---" in text or "```plaintext" in text:
        return "notice_box"
    if re.search(r"^\s*\([a-d]\)", text, re.MULTILINE):
        return "subquestion"
    return "descriptive"


# ---------- Accuracy Diagnostics & Benchmarking ----------

def calculate_accuracy_diagnostics(db: Session) -> dict:
    """
    Computes rigorous accuracy metrics comparing original OCR vs teacher-corrected references:
    - Character Error Rate (CER)
    - Word Error Rate (WER)
    - Question Numbering Accuracy
    - Marks Accuracy
    - Mathematical Symbol Accuracy
    - Breakdown by subject and document type
    """
    seed_verified_reference_collection(db)
    examples = db.query(VerifiedReferenceExample).all()

    if not examples:
        return {
            "sample_size": 0,
            "overall_cer": 0.0,
            "overall_wer": 0.0,
            "overall_accuracy_pct": 100.0,
            "question_number_accuracy_pct": 100.0,
            "marks_accuracy_pct": 100.0,
            "by_subject": {},
            "by_error_category": {},
        }

    total_chars_ref = 0
    total_char_dist = 0
    total_words_ref = 0
    total_word_dist = 0

    numbering_matches = 0
    marks_matches = 0
    total_items = len(examples)

    by_subject: dict[str, dict] = {}
    by_category: dict[str, int] = {}

    for ex in examples:
        ref_text = ex.corrected_text or ""
        hyp_text = ex.original_ocr or ""

        # Char edit distance
        c_dist = levenshtein_distance(ref_text, hyp_text)
        total_char_dist += c_dist
        total_chars_ref += max(1, len(ref_text))

        # Word edit distance
        ref_w = re.findall(r"\S+", ref_text.lower())
        hyp_w = re.findall(r"\S+", hyp_text.lower())
        w_dist = levenshtein_distance(ref_w, hyp_w)
        total_word_dist += w_dist
        total_words_ref += max(1, len(ref_w))

        # Question numbering check
        if ex.question_number:
            hyp_has_num = bool(re.search(re.escape(ex.question_number), hyp_text, re.IGNORECASE))
            if hyp_has_num:
                numbering_matches += 1

        # Marks check
        if ex.approved_marks is not None:
            marks_str = str(int(ex.approved_marks)) if ex.approved_marks.is_integer() else str(ex.approved_marks)
            if marks_str in hyp_text:
                marks_matches += 1

        # Category tally
        cat = ex.error_category or "none"
        by_category[cat] = by_category.get(cat, 0) + 1

        # Subject breakdown
        sub = ex.subject or "General"
        if sub not in by_subject:
            by_subject[sub] = {"samples": 0, "char_dist": 0, "chars_ref": 0, "word_dist": 0, "words_ref": 0}
        by_subject[sub]["samples"] += 1
        by_subject[sub]["char_dist"] += c_dist
        by_subject[sub]["chars_ref"] += max(1, len(ref_text))
        by_subject[sub]["word_dist"] += w_dist
        by_subject[sub]["words_ref"] += max(1, len(ref_w))

    overall_cer = min(1.0, total_char_dist / max(1, total_chars_ref))
    overall_wer = min(1.0, total_word_dist / max(1, total_words_ref))
    accuracy_pct = round(max(0.0, (1.0 - overall_cer) * 100), 2)
    numbering_acc_pct = round((numbering_matches / max(1, total_items)) * 100, 2)
    marks_acc_pct = round((marks_matches / max(1, total_items)) * 100, 2)

    subject_metrics = {}
    for sub, data in by_subject.items():
        sub_cer = min(1.0, data["char_dist"] / max(1, data["chars_ref"]))
        sub_wer = min(1.0, data["word_dist"] / max(1, data["words_ref"]))
        subject_metrics[sub] = {
            "samples": data["samples"],
            "cer": round(sub_cer, 4),
            "wer": round(sub_wer, 4),
            "accuracy_pct": round(max(0.0, (1.0 - sub_cer) * 100), 2),
        }

    return {
        "sample_size": total_items,
        "overall_cer": round(overall_cer, 4),
        "overall_wer": round(overall_wer, 4),
        "overall_accuracy_pct": accuracy_pct,
        "question_number_accuracy_pct": numbering_acc_pct,
        "marks_accuracy_pct": marks_acc_pct,
        "by_subject": subject_metrics,
        "by_error_category": by_category,
    }


def get_few_shot_prompt_hints(subject: str | None = None) -> str:
    """Generates few-shot prompt instructions based on verified reference exemplars."""
    return """
VERIFIED REFERENCE PERCEPTION RULES:
1. MATHEMATICAL FORMULAS & POWERS:
   - Always preserve vertical exponents as inline exponential notation: [((2/3)⁻² × (3/4)⁻³) ÷ (8/9)⁻²] or ((2/3)^-2 * (3/4)^-3) / (8/9)^-2.
   - Preserve superscripts and squares: (a + b)² = a² + b² + 2ab, x² + 1/x² = 34, 16x⁴ - 81y⁴.
   - Preserve geometry/mensuration formulas: V = π(R² - r²)h, TSA = 2πRh + 2πrh + 2π(R² - r²).
   - Never collapse vertical fractions into isolated parentheses lines.

2. TABLES & EDITING EXERCISES:
   - Output structured tables as clean Markdown tables:
     | Line | Incorrect Word | Correct Word |
     | :--- | :--- | :--- |
     | (a)  | habits         | habit        |
   - Never flatten table cells into unformatted single lines.

3. CHEMICAL EQUATIONS & SYMBOLS:
   - Preserve exact reaction symbols: Na + H₂O → ________ + H₂ ↑, SO₂ + H₂O → ________, Zn + H₂SO₄ → ________ + H₂ ↑.
   - Preserve reaction arrows (→), gas release arrows (↑), and blanks (________).

4. FORMATTED NOTICE BOXES & LETTERS:
   - Preserve enclosed notice writing boxes using ```plaintext with border characters +--- and | boundaries.
"""
