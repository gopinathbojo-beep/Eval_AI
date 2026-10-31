"""A school starts with every CBSE subject (cbse/subjects.json); its management sets up classes and subjects and
assigns teachers theirs, teachers only run exams in what they are assigned."""
from app.cbse.common import standards


def test_teachers_cannot_set_up_classes_or_subjects(client, auth, teach):
    sub = client.post("/api/subjects", headers=auth, json={"name": "Setup Physics"})
    cls = client.post("/api/classes", headers=auth, json={"std": "12", "section": "Setup"})
    assert sub.status_code == 201 and cls.status_code == 201
    for method, path, body in (("post", "/api/subjects", {"name": "My own subject"}),
                               ("patch", f"/api/subjects/{sub.json()['id']}", {"name": "Renamed"}),
                               ("delete", f"/api/subjects/{sub.json()['id']}", None),
                               ("post", "/api/classes", {"std": "10", "section": "Mine"}),
                               ("patch", f"/api/classes/{cls.json()['id']}", {"std": "10", "section": "Z"}),
                               ("delete", f"/api/classes/{cls.json()['id']}", None)):
        r = client.request(method.upper(), path, headers=teach, json=body)
        assert r.status_code == 403 and r.json()["code"] == "MANAGEMENT_REQUIRED", (method, path, r.text)


def test_a_new_school_gets_every_reference_subject_once():
    from app.database import SessionLocal
    from app.models import Subject, Teacher, Workspace
    from app.services.school_setup import default_subjects
    db = SessionLocal()
    try:
        owner = Teacher(name="Setup Manager", email="setup-manager@school.org", role="MANAGEMENT")
        db.add(owner)
        db.flush()
        school = Workspace(kind="SCHOOL", name="Setup School", owner_id=owner.id)
        db.add(school)
        db.flush()
        assert len(default_subjects(db, school)) == len(standards.catalog()) == 18
        assert default_subjects(db, school) == []  # running again adds nothing
        names = {s.name for s in db.query(Subject).filter_by(teacher_id=owner.id, workspace_id=school.id)}
        assert {"Mathematics Basic", "Mathematics Standard", "Science", "Physics", "Accountancy", "Tamil"} <= names
    finally:
        db.rollback()
        db.close()
