"""Production creation gates plus historical compatibility and scheme arithmetic."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import json
import hashlib
import uuid
import pytest
from app.cbse.catalog import PROFILES, VERSION, get_profile
from app.cbse.extraction import (
    Node,
    tree_total,
    tree_issues,
    merge_nodes,
    Page,
    Fragment,
)
from app.cbse.grading import validate_result
from app.cbse.validation import validate
from app.ocr.schemas import EvaluationResult
from app.formatter.common.mark_rules import EvaluationValidationError
from app.database import SessionLocal
from app.models import (
    Exam,
    ExamQuestion,
    AnswerKey,
    QuestionPaperDocument,
    AnswerKeyDocument,
    Evaluation,
    EvaluationItem,
    AnswerSheetDocument,
    Student,
    StudentAnswer,
    AuditLog,
)


@pytest.fixture(autouse=True)
def isolated_browser_cookies(client, monkeypatch):
    from app.login_limiter import LoginLimiter
    from app.routes import core, registration

    monkeypatch.setattr(core, "login_limiter", LoginLimiter())
    monkeypatch.setattr(registration, "register_limiter", LoginLimiter())
    yield
    client.cookies.clear()


def point(name, marks=1):
    return {
        "id": name,
        "kind": "point",
        "label": name,
        "text": "Marking point",
        "marks": marks,
        "children": [],
    }


def make_board(client, auth, with_key=True):
    cls = client.post("/api/classes", headers=auth, json={"name": "10-A"}).json()
    sub = client.post(
        "/api/subjects",
        headers=auth,
        json={"name": "Computer Applications", "code": "165"},
    ).json()
    response = client.post(
        "/api/exams",
        headers=auth,
        json={"name": "CBSE test", "class_id": cls["id"], "subject_id": sub["id"]},
    )
    assert response.status_code == 201, response.text
    eid = response.json()["id"]
    with SessionLocal() as db:
        exam = db.get(Exam, eid)
        meta = {
            "class_level": 10,
            "subject_code": "165",
            "maximum_marks": 50,
            "duration_minutes": 120,
            "stated_question_count": 26,
        }
        docs = []
        for model in (
            [QuestionPaperDocument, AnswerKeyDocument]
            if with_key
            else [QuestionPaperDocument]
        ):
            d = model(
                exam_id=eid,
                original_filename="source.pdf",
                original_file="unused.pdf",
                mime_type="application/pdf",
                file_size=100,
                status="READY",
                pages=[{"page_number": 1, "ocr_status": "OK"}],
                extraction={
                    "metadata": deepcopy(meta),
                    "instructions": ["Credit correct equivalent expression."],
                    "issues": [],
                },
            )
            db.add(d)
            db.flush()
            docs.append(d)
        for sec in get_profile(exam.standard_profile_id)["sections"]:
            for n in range(sec["start"], sec["end"] + 1):
                tree = point(f"q{n}", sec["each"])
                q = ExamQuestion(
                    exam_id=eid,
                    document_id=docs[0].id,
                    display_number=str(n),
                    normalized_number=str(n),
                    position=n,
                    question_text=f"Question {n}",
                    max_marks=sec["each"],
                    section=sec["key"],
                    structure={"root": n, "tree": tree, "issues": []},
                    verification_status="UNVERIFIED",
                )
                db.add(q)
                db.flush()
                if with_key:
                    db.add(
                        AnswerKey(
                            exam_id=eid,
                            document_id=docs[-1].id,
                            exam_question_id=q.id,
                            raw_question_number=str(n),
                            normalized_number=str(n),
                            answer_text="Expected answer",
                            marks=sec["each"],
                            mapping_status="MAPPED",
                            verification_status="UNVERIFIED",
                            rubric={
                                "cbse_tree": deepcopy(tree),
                                "problems": [],
                                "points": [],
                                "notes": [],
                                "deductions": [],
                                "total": sec["each"],
                            },
                            rubric_status="UNREVIEWED",
                        )
                    )
        exam.status = "QUESTIONS_EXTRACTED"
        db.commit()
    return eid, cls["id"]


@pytest.mark.parametrize("p", PROFILES, ids=lambda p: p["id"])
def test_catalog_is_complete_and_internally_consistent(p):
    assert len(PROFILES) == 21
    if p["upload_driven"]:
        assert p["question_count"] == 0 and p["sections"] == [] and p["parent_marks"] == []
        assert p["duration_minutes"] == 180 and p["total_marks"] == 80
        return
    assert sum(s["marks"] for s in p["sections"]) == p["total_marks"]
    assert [n for s in p["sections"] for n in range(s["start"], s["end"] + 1)] == list(
        range(1, p["question_count"] + 1)
    )
    if p["parent_marks"]:
        assert len(p["parent_marks"]) == p["question_count"]
        for sec in p["sections"]:
            assert sum(p["parent_marks"][sec["start"] - 1 : sec["end"]]) == sec["marks"]


def test_all_supplied_source_pairs_are_fingerprinted():
    import app.cbse.catalog as catalog

    manifest = json.loads(
        Path(catalog.__file__).with_name("sources.json").read_text(encoding="utf-8")
    )
    assert len(manifest) == 36 and sum(s["page_count"] for s in manifest) == 362
    root = Path(__file__).resolve().parents[2]
    for p in (p for p in PROFILES if not p["upload_driven"]):
        pair = [s for s in manifest if s["profile_id"] == p["id"]]
        assert {s["kind"] for s in pair} == {"question-paper", "answer-key"}
        for source in pair:
            assert (
                len(source["sha256"]) == 64
                and source["text_pages"] == source["page_count"]
            )
            file = root / source["path"]
            if file.exists():
                assert hashlib.sha256(file.read_bytes()).hexdigest() == source["sha256"]


def test_additive_migration_preserves_legacy_exam_and_supports_postgresql_ddl(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, MetaData, Table, select
    from datetime import datetime, timezone

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "20261030_uploads")
        old = Table("exams", MetaData(), autoload_with=connection)
        connection.execute(
            old.insert().values(
                id="legacy",
                teacher_id="old-owner",
                name="Old short exam",
                academic_year="2025-26",
                class_id="old-class",
                subject_id="old-subject",
                exam_type="Unit test",
                total_marks=10,
                status="DRAFT",
                created_at=datetime.now(timezone.utc),
            )
        )
        command.upgrade(config, "head")
        current = Table("exams", MetaData(), autoload_with=connection)
        row = (
            connection.execute(select(current).where(current.c.id == "legacy"))
            .mappings()
            .one()
        )
        assert (
            row["name"] == "Old short exam"
            and row["total_marks"] == 10
            and row["standard_profile_id"] is None
        )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from importlib.util import spec_from_file_location, module_from_spec
    from io import StringIO

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    spec = spec_from_file_location(
        "cbse_revision",
        Path(__file__).resolve().parents[1] / "migrations/versions/20261031_cbse.py",
    )
    revision = module_from_spec(spec)
    spec.loader.exec_module(revision)
    with Operations.context(context):
        revision.upgrade()
    assert "ALTER TABLE exams ADD COLUMN standard_profile_id" in output.getvalue()
    assert (
        "ALTER TABLE answer_key_documents ADD COLUMN extraction JSON"
        in output.getvalue()
    )


def test_production_creation_requires_exact_variant_and_full_pattern(client, auth):
    cls = client.post("/api/classes", headers=auth, json={"name": "10-A"}).json()
    sub = client.post("/api/subjects", headers=auth, json={"name": "Maths"}).json()
    body = {"name": "Board exam", "class_id": cls["id"], "subject_id": sub["id"]}
    assert client.post("/api/exams", headers=auth, json=body).status_code == 400
    body["standard_profile_id"] = "cbse-10-041"
    for invalid in (
        {"total_marks": 20},
        {"duration_minutes": 45},
        {"academic_year": "2025-26"},
    ):
        assert (
            client.post("/api/exams", headers=auth, json=body | invalid).status_code
            == 400
        )
    result = client.post("/api/exams", headers=auth, json=body)
    assert result.status_code == 201, result.text
    data = result.json()
    assert (
        data["total_marks"],
        data["duration_minutes"],
        data["standard_version"],
    ) == (80, 180, VERSION)
    assert (
        client.patch(
            f"/api/exams/{data['id']}", headers=auth, json={"total_marks": 20}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/exams",
            headers=auth,
            json=body | {"standard_profile_id": "cbse-12-042"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ("missing_question", "MISSING_QUESTIONS"),
        ("wrong_section", "SECTION_MISMATCH"),
        ("marks", "QUESTION_ALLOCATION"),
        ("bad_tree", "QUESTION_TOTAL"),
        ("scheme_marks", "SCHEME_TOTAL"),
        ("unread_page", "PAGES_INCOMPLETE"),
        ("wrong_code", "METADATA_MISMATCH"),
        ("missing_key", "KEY_COVERAGE"),
        ("page_count", "PAGE_COUNT_MISMATCH"),
        ("source_issue", "EXTRACTION_REVIEW"),
    ],
)
def test_source_diagnostics_do_not_add_cbse_verification_gates(client, auth, change, code):
    eid, _ = make_board(client, auth)
    with SessionLocal() as db:
        e = db.get(Exam, eid)
        q = db.query(ExamQuestion).filter_by(exam_id=eid, display_number="1").one()
        doc = db.query(QuestionPaperDocument).filter_by(exam_id=eid).one()
        k = db.query(AnswerKey).filter_by(exam_question_id=q.id).one()
        if change == "missing_question":
            k.exam_question_id = None
            db.delete(q)
        elif change == "wrong_section":
            q.section = "E"
        elif change == "marks":
            q.max_marks = 2
        elif change == "bad_tree":
            q.structure = {**q.structure, "tree": point("q1", 2)}
        elif change == "scheme_marks":
            k.marks = 2
        elif change == "unread_page":
            doc.pages = [{"page_number": 1, "ocr_status": "FAILED"}]
        elif change == "wrong_code":
            doc.extraction = {
                **doc.extraction,
                "metadata": {**doc.extraction["metadata"], "subject_code": "184"},
            }
        elif change == "missing_key":
            db.delete(k)
        elif change == "page_count":
            doc.extraction = {
                **doc.extraction,
                "metadata": {**doc.extraction["metadata"], "printed_page_count": 2},
            }
        elif change == "source_issue":
            doc.extraction = {
                **doc.extraction,
                "issues": ["Unclear choice instruction"],
            }
            k.rubric = {**k.rubric, "problems": ["Board-pattern extraction note"]}
        db.commit()
        result = validate(db, e, "scheme")
        assert code in {i["code"] for i in result["issues"]}
        assert not result["valid"]
        e.status = "ANSWER_KEY_UPLOADED"
        db.commit()
    response = client.post(f"/api/exams/{eid}/answer-keys/verify", headers=auth)
    assert response.json().get("code") != "CBSE_NOT_READY"
    if change in {"wrong_section", "bad_tree", "wrong_code", "page_count", "source_issue", "missing_question"}:
        assert response.status_code == 200, response.text
    elif change in {"marks", "scheme_marks", "missing_key"}:
        assert response.status_code == 400, response.text


def test_accepted_questions_continue_to_waiting_key_despite_cbse_findings(client, auth, monkeypatch):
    from app.routes import documents

    eid, _ = make_board(client, auth)
    queued = []
    monkeypatch.setattr(documents, "submit", lambda *args: queued.append(args))
    with SessionLocal() as db:
        q = db.query(ExamQuestion).filter_by(exam_id=eid).first()
        q.section = None
        q.structure = {**q.structure, "issues": ["Review source allocation"]}
        key_doc = db.query(AnswerKeyDocument).filter_by(exam_id=eid).one()
        key_doc.status = "WAITING"
        db.commit()
    prefix = f"/api/exams/{eid}"
    # Basic review is still required, even though full board checks are deferred.
    rejected = client.post(prefix + "/questions/verify", headers=auth)
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "QUESTIONS_NOT_READY"
    assert client.post(prefix + "/questions/accept-valid", headers=auth).status_code == 200
    result = client.post(prefix + "/questions/verify", headers=auth)
    assert result.status_code == 200, result.text
    assert result.json()["answer_key_started"] is True
    assert len(queued) == 1 and queued[0][2] == "answer-key"
    with SessionLocal() as db:
        exam = db.get(Exam, eid)
        assert exam.status == "ANSWER_KEY_UPLOADED"
        # Diagnostics are optional, never a prerequisite for moving forward.
        assert exam.standard_validation is None


def test_valid_pair_verifies_and_review_invalidates_both_stages(client, auth):
    eid, _ = make_board(client, auth)
    path = f"/api/exams/{eid}"
    assert client.get(path + "/standard-validation?phase=scheme", headers=auth).json()[
        "valid"
    ]
    assert (
        client.post(path + "/questions/accept-valid", headers=auth).status_code == 200
    )
    result = client.post(path + "/questions/verify", headers=auth)
    assert result.status_code == 200, result.text
    result = client.post(path + "/answer-keys/verify", headers=auth)
    assert result.status_code == 200, result.text
    assert client.get(path + "/standard-validation", headers=auth).json()["valid"]
    with SessionLocal() as db:
        k = db.query(AnswerKey).filter_by(exam_id=eid).first()
        kid = k.id
        tree = k.rubric["cbse_tree"]
    result = client.post(
        path + "/standard-review",
        headers=auth,
        json={
            "target": "key",
            "id": kid,
            "tree": tree,
            "reason": "Checked original scheme",
        },
    )
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        assert db.get(Exam, eid).status == "QUESTIONS_EXTRACTED"
        assert db.get(AnswerKey, kid).rubric_status == "UNREVIEWED"
        assert all(
            q.verification_status == "UNVERIFIED"
            for q in db.query(ExamQuestion).filter_by(exam_id=eid)
        )
        event = (
            db.query(AuditLog)
            .filter_by(exam_id=eid, action="cbse_source_corrected")
            .one()
        )
        assert event.teacher_id and event.workspace_id


def test_choice_arithmetic_fractional_marks_and_no_universal_cap():
    tree = {
        "id": "root",
        "kind": "all",
        "children": [
            point("method", 0.25),
            {
                "id": "or",
                "kind": "choose",
                "limit": 1,
                "children": [point("a", 1.5), point("b", 1.5)],
            },
        ],
    }
    assert tree_total(tree, {}) == 1.75
    key = NS(rubric={"cbse_tree": tree})
    q = NS(max_marks=1.75)
    result = EvaluationResult(
        marks_awarded=99,
        criterion_awards=[
            {"id": k, "marks": v, "evidence": "Visible working"}
            for k, v in {"method": 0.25, "a": 0.25, "b": 1}.items()
        ],
    )
    assert validate_result(result, q, key, {}).marks_awarded == 1.25
    result.criterion_awards[0]["marks"] = 1
    with pytest.raises(EvaluationValidationError):
        validate_result(result, q, key, {})


def test_branch_and_accessibility_alternatives_do_not_add_marks():
    tree = {
        "id": "q",
        "kind": "all",
        "marks": 2,
        "children": [
            point("regular", 2) | {"audience": "standard"},
            point("accessible", 2) | {"audience": "accessible"},
        ],
    }
    assert not tree_issues(tree, {"accessibility": "standard"})
    assert tree_total(tree, {"accessibility": "accessible"}) == 2
    tree["children"][1]["marks"] = 3
    assert tree_issues(tree, {"accessibility": "accessible"})


def test_unknown_missing_duplicate_criteria_and_multiple_mcq_answers():
    key = NS(rubric={"cbse_tree": point("q", 1)})
    q = NS(max_marks=1)
    result = EvaluationResult(
        marks_awarded=1,
        criterion_awards=[
            {"id": "q", "marks": 1, "evidence": "A and B", "multiple_answers": True}
        ],
    )
    assert validate_result(result, q, key, {}).marks_awarded == 0
    mcq_key = NS(rubric={"cbse_tree": point("q", 1) | {"response_type": "mcq"}})
    # an MCQ is right or wrong: a half mark is 0, not an error
    assert validate_result(
        EvaluationResult(marks_awarded=0.5, criterion_awards=[{"id": "q", "marks": 0.5, "evidence": "A"}]),
        q, mcq_key, {},
    ).marks_awarded == 0
    for awards in (
        [],
        [{"id": "other", "marks": 1}],
        [{"id": "q", "marks": 1}],
        [{"id": "q", "marks": 1, "evidence": "A"}] * 2,
    ):
        with pytest.raises(EvaluationValidationError):
            validate_result(
                EvaluationResult(marks_awarded=1, criterion_awards=awards), q, key, {}
            )


def test_one_criterion_split_into_awards_with_the_same_id_is_added_up():
    # the model graded part I and part II of a one-criterion question as two awards under the same id
    key = NS(rubric={"cbse_tree": point("q19", 3)})
    q = NS(max_marks=3)
    awards = [{"id": "q19", "marks": 1.0, "evidence": "", "evidence_quotes": ["6,30,000 / 90"]},
              {"id": "q19", "marks": 0.0, "evidence": "", "evidence_quotes": []}]
    student = "i, Number of debenture = 6,30,000 / 90 = 7000"
    got = validate_result(EvaluationResult(marks_awarded=1, criterion_awards=awards), q, key, {}, student)
    assert got.marks_awarded == 1
    over = [{"id": "q19", "marks": 2, "evidence_quotes": ["6,30,000 / 90"]}] * 2   # added up past the allocation
    with pytest.raises(EvaluationValidationError):
        validate_result(EvaluationResult(marks_awarded=3, criterion_awards=over), q, key, {}, student)


def test_only_source_defined_deductions_within_their_limit_are_applied():
    tree = point("answer", 5) | {
        "deductions": [
            {
                "id": "accuracy",
                "maximum": 1,
                "text": "Deduct up to one mark for accuracy",
            }
        ]
    }
    key = NS(rubric={"cbse_tree": tree})
    q = NS(max_marks=5)
    result = EvaluationResult(
        marks_awarded=5,
        criterion_awards=[{"id": "answer", "marks": 5, "evidence": "Written answer"}],
        deductions=[
            {
                "id": "accuracy",
                "marks": 0.75,
                "reason": "Three printed accuracy criteria missed",
            }
        ],
    )
    assert validate_result(result, q, key, {}, "Written answer").marks_awarded == 4.25
    result.deductions[0]["marks"] = 1.25
    with pytest.raises(EvaluationValidationError):
        validate_result(result, q, key, {})
    result.deductions = [{"id": "invented", "marks": 0.5, "reason": "Made up rule"}]
    with pytest.raises(EvaluationValidationError):
        validate_result(result, q, key, {})
    result.deductions = []
    with pytest.raises(EvaluationValidationError):
        validate_result(result, q, key, {}, "Different student text")


def test_continuations_merge_and_conflicting_allocations_require_review():
    roots, issues = merge_nodes(
        [
            {"id": "q1", "kind": "all", "marks": 2, "children": [point("a", 1)]},
            {"id": "q1", "kind": "all", "marks": 2, "children": [point("b", 1)]},
        ]
    )
    assert not issues and tree_total(roots[0], {}) == 2
    _, issues = merge_nodes([point("q1", 1), point("q1", 2)])
    assert issues
    with pytest.raises(ValueError):
        Node.model_validate(point("x", float("nan")))


def test_cross_page_parts_derive_total_from_source_and_duplicate_roots_are_flagged():
    from app.cbse.build import collect, combined, review_reason

    first = Page(
        page_number=1,
        fragments=[
            Fragment(
                root=1,
                text="Part a",
                tree=Node.model_validate(
                    {"id": "q1", "kind": "all", "children": [point("a", 1)]}
                ),
            )
        ],
    )
    second = Page(
        page_number=2,
        fragments=[
            Fragment(
                root=1,
                text="Part b",
                continues=True,
                tree=Node.model_validate(
                    {"id": "q1", "kind": "all", "children": [point("b", 2)]}
                ),
            )
        ],
    )
    roots = collect(NS(), [({"page_number": 1}, first), ({"page_number": 2}, second)])
    _, _, issues, marks, _ = combined(roots[1])
    assert not issues and marks == 3
    # a page-top piece under the previous page's last number is that question carried over, even when the model
    # did not say so (CBSE papers print the marks only where a question starts)
    second.fragments[0].continues = False
    roots = collect(NS(), [({"page_number": 1}, first), ({"page_number": 2}, second)])
    _, _, issues, marks, _ = combined(roots[1])
    assert not issues and marks == 3
    # the same number again after another question is a genuine duplicate and is flagged
    second.fragments = [
        Fragment(root=2, text="Question two", tree=Node.model_validate({"id": "q2", "kind": "all", "children": [point("c", 1)]})),
        Fragment(root=1, text="Part b", tree=Node.model_validate({"id": "q1", "kind": "all", "children": [point("b", 2)]})),
    ]
    roots = collect(NS(), [({"page_number": 1}, first), ({"page_number": 2}, second)])
    assert combined(roots[1])[2]
    full_issues = ["source conflict " + ("x" * 200), "another " + ("y" * 200)]
    assert len(review_reason(full_issues)) == 300
    assert review_reason(full_issues).endswith("...")


def test_cbse_visual_evidence_is_tightly_cropped_and_described(tmp_path, monkeypatch):
    from PIL import Image
    from app.cbse import build

    source = tmp_path / "page.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    fragment = Fragment.model_validate(
        {
            "root": 8,
            "text": "Refer to the circuit diagram.",
            "visuals": [
                {
                    "kind": "diagram",
                    "description": "Circuit with a cell and two labelled resistors.",
                    "labels": ["R1", "R2"],
                    "bbox": {"x": 100, "y": 200, "width": 300, "height": 250},
                }
            ],
        }
    )
    page = {
        "page_number": 2,
        "source_file": "page.png",
        "ocr_width": 1000,
        "ocr_height": 1400,
        "width": 1000,
        "height": 1400,
    }
    monkeypatch.setattr(build, "abs_path", lambda _: source)
    monkeypatch.setattr(build, "rel", lambda value: str(value))
    visuals = build.crop_visuals([(page, fragment)], tmp_path, "q8")
    assert len(visuals) == 1
    assert visuals[0]["kind"] == "diagram"
    assert visuals[0]["labels"] == ["R1", "R2"]
    assert Path(visuals[0]["crop_file"]).exists()
    with Image.open(visuals[0]["crop_file"]) as crop:
        assert crop.width == 300 and crop.height == 250


def test_workspace_isolation_on_standards_review(client, auth):
    eid, _ = make_board(client, auth)
    outsider = client.post(
        "/api/auth/register",
        headers={"X-Requested-With": "EvalAI"},
        json={
            "name": "Other parent",
            "email": f"cbse-{uuid.uuid4()}@example.com",
            "password": "Password-12345",
            "role": "PARENT",
        },
    )
    assert outsider.status_code == 201, outsider.text
    login = client.post(
        "/api/auth/login",
        json={
            "email": outsider.json()["teacher"]["email"],
            "password": "Password-12345",
        },
    )
    token = {"Authorization": "Bearer " + login.json()["access_token"]}
    profile = {
        "name": "Other parent",
        "phone": "9876543210",
        "child_name": "One child",
        "child_class": "10",
    }
    assert (
        client.put("/api/auth/profile", headers=token, json=profile).status_code == 200
    )
    assert (
        client.get(f"/api/exams/{eid}/standard-validation", headers=token).status_code
        == 404
    )
    for path in ("promote-block", "dismiss-block"):
        assert (
            client.post(
                f"/api/exams/{eid}/{path}",
                headers=token,
                json={"text": "Foreign source block"},
            ).status_code
            == 404
        )
    assert (
        client.post(
            f"/api/exams/{eid}/standard-review",
            headers=token,
            json={
                "target": "options",
                "options": {"accessibility": "standard"},
                "reason": "No access",
            },
        ).status_code
        == 404
    )


def test_worker_no_longer_blocks_on_cbse_pattern_checks(client, auth):
    from app.services.evaluation_service import run_evaluation

    eid, cid = make_board(client, auth, False)
    with SessionLocal() as db:
        student = Student(
            class_id=cid, name="Test child", roll_number=str(uuid.uuid4())
        )
        db.add(student)
        db.flush()
        sheet = AnswerSheetDocument(
            exam_id=eid,
            student_id=student.id,
            original_filename="sheet.pdf",
            original_file="sheet.pdf",
            mime_type="application/pdf",
            file_size=1,
            status="READY",
        )
        db.add(sheet)
        db.flush()
        ev = Evaluation(
            exam_id=eid,
            student_id=student.id,
            answer_sheet_id=sheet.id,
            status="READY",
            run_status="RUNNING",
        )
        db.add(ev)
        db.flush()
        ev_id = ev.id
        db.get(Exam, eid).status = "READY_FOR_EVALUATION"
        db.commit()
    run_evaluation(ev_id)
    with SessionLocal() as db:
        assert db.get(Evaluation, ev_id).run_status == "DONE"
        assert db.query(EvaluationItem).filter_by(evaluation_id=ev_id).first()


@pytest.mark.parametrize("role", ["MANAGEMENT", "PARENT"])
def test_full_upload_pipeline_and_reviewed_scheme_grading(
    client, auth, monkeypatch, role
):
    from tests.conftest import make_pdf
    from app.services import pipeline, evaluation_service

    p = get_profile("cbse-10-165")
    if role == "PARENT":
        email = f"parent-board-{uuid.uuid4()}@example.com"
        result = client.post(
            "/api/auth/register",
            headers={"X-Requested-With": "EvalAI"},
            json={
                "name": "Board parent",
                "email": email,
                "password": "Password-12345",
                "role": "PARENT",
            },
        )
        assert result.status_code == 201, result.text
        token = client.post(
            "/api/auth/login", json={"email": email, "password": "Password-12345"}
        ).json()["access_token"]
        auth = {"Authorization": "Bearer " + token}
        result = client.put(
            "/api/auth/profile",
            headers=auth,
            json={
                "name": "Board parent",
                "phone": "9876543210",
                "child_name": "Pipeline child",
                "child_class": "10",
            },
        )
        assert result.status_code == 200, result.text
        cls = client.get("/api/classes", headers=auth).json()[0]
    else:
        cls = client.post("/api/classes", headers=auth, json={"name": "10-B"}).json()
    sub = client.post(
        "/api/subjects", headers=auth, json={"name": p["name"], "code": p["code"]}
    ).json()
    if role == "TEACHER":
        from app.models import Teacher, TeacherAssignment, SchoolClass
        from app.security import create_token
        from datetime import datetime, timezone

        with SessionLocal() as db:
            school = db.get(SchoolClass, cls["id"])
            teacher = Teacher(
                name="Assigned teacher",
                password_hash="test-only-unused-hash",
                email=f"teacher-board-{uuid.uuid4()}@example.com",
                role="TEACHER",
                workspace_id=school.workspace_id,
                profile_completed_at=datetime.now(timezone.utc),
            )
            db.add(teacher)
            db.flush()
            db.add(
                TeacherAssignment(
                    teacher_id=teacher.id, class_id=cls["id"], subject_id=sub["id"]
                )
            )
            db.commit()
            auth = {
                "Authorization": "Bearer "
                + create_token(teacher.id, teacher.session_version)
            }
    e = client.post(
        "/api/exams",
        headers=auth,
        json={
            "name": "Uploaded board paper",
            "class_id": cls["id"],
            "subject_id": sub["id"],
        },
    ).json()
    eid = e["id"]

    def extracted(system, user, schema, image_path=None, **kwargs):
        import re

        n = int(re.search(r"Read page (\d+)", user).group(1))
        fragments = []
        for root in range(1 if n == 1 else 14, 14 if n == 1 else 27):
            sec = next(s for s in p["sections"] if s["start"] <= root <= s["end"])
            fragments.append(
                Fragment(
                    root=root,
                    text=f"Source content for {root}",
                    section=sec["key"],
                    marks=sec["each"],
                    tree=Node.model_validate(point(f"q{root}", sec["each"])),
                )
            )
        parsed = Page(
            page_number=n,
            metadata={
                "class_level": 10,
                "subject_code": "165",
                "maximum_marks": 50,
                "duration_minutes": 120,
                "printed_page_count": 2,
            },
            instructions=[
                "Accept correct equivalent expression; credit only written working."
            ],
            fragments=fragments,
        )
        return NS(parsed=parsed, raw=parsed.model_dump_json(), attempts=1)

    monkeypatch.setattr(pipeline, "chat_structured", extracted)
    prefix = f"/api/exams/{eid}"
    # Upload scheme early; it must wait for the canonical questions.
    assert (
        client.post(
            prefix + "/answer-key",
            headers=auth,
            files={"file": ("scheme.pdf", make_pdf(2), "application/pdf")},
        ).status_code
        == 202
    )
    assert (
        client.post(
            prefix + "/question-paper",
            headers=auth,
            files={"file": ("paper.pdf", make_pdf(2), "application/pdf")},
        ).status_code
        == 202
    )
    info = client.get(prefix + "/standard-validation?phase=paper", headers=auth).json()
    assert info["valid"], info["issues"]
    assert (
        client.post(prefix + "/questions/accept-valid", headers=auth).status_code == 200
    )
    result = client.post(prefix + "/questions/verify", headers=auth)
    assert result.status_code == 200, result.text
    result = client.post(prefix + "/answer-keys/verify", headers=auth)
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        q = db.query(ExamQuestion).filter_by(exam_id=eid, display_number="1").one()
        student = (
            db.query(Student).filter_by(class_id=cls["id"]).first()
            if role == "PARENT"
            else None
        )
        if student is None:
            student = Student(
                class_id=cls["id"], name="Pipeline child", roll_number=str(uuid.uuid4())
            )
            db.add(student)
            db.flush()
        sheet = AnswerSheetDocument(
            exam_id=eid,
            student_id=student.id,
            original_filename="sheet.pdf",
            original_file="unused.pdf",
            mime_type="application/pdf",
            file_size=1,
            status="READY",
        )
        db.add(sheet)
        db.flush()
        ev = Evaluation(
            exam_id=eid, student_id=student.id, answer_sheet_id=sheet.id, status="READY"
        )
        db.add(ev)
        db.flush()
        answer = StudentAnswer(
            evaluation_id=ev.id,
            exam_question_id=q.id,
            answer_text="Visible answer",
            status="MAPPED",
            position=1,
        )
        db.add(answer)
        db.commit()
        vid = ev.id

    def grade(system, prompt, schema, **kwargs):
        assert (
            "GENERAL EXAMINER INSTRUCTIONS" in prompt
            and "Accept correct equivalent expression" in prompt
        )
        assert "0.5 steps" not in prompt and "at most 0.5" not in system
        return NS(
            parsed=EvaluationResult(
                marks_awarded=1,
                criterion_awards=[
                    {"id": "q1", "marks": 1, "evidence": "Visible answer"}
                ],
                feedback="Correct",
            ),
            raw="{}",
        )

    monkeypatch.setattr(evaluation_service, "chat_structured", grade)
    result = client.post(f"/api/evaluations/{vid}/run", headers=auth)
    assert result.status_code == 202, result.text
    with SessionLocal() as db:
        assert db.get(Evaluation, vid).run_status == "DONE"
        item = (
            db.query(EvaluationItem)
            .filter_by(evaluation_id=vid, exam_question_id=q.id)
            .one()
        )
        assert item.ai_marks == 1
