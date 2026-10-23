"""
Tests for Classes, Subjects, and Students CRUD and dynamic Marksheet export.
"""

from __future__ import annotations
import pytest


def test_classes_crud(client, auth):
    c, h = client, auth

    # 1. Create class
    r = c.post("/api/classes", headers=h, json={"name": "Grade 7-Z"})
    assert r.status_code == 201, r.text
    cl_id = r.json()["id"]
    assert r.json()["name"] == "Grade 7-Z"

    # 2. Update class name
    r_update = c.patch(f"/api/classes/{cl_id}", headers=h, json={"name": "Grade 7-X"})
    assert r_update.status_code == 200, r_update.text
    assert r_update.json()["name"] == "Grade 7-X"

    # 3. List classes
    r_list = c.get("/api/classes", headers=h)
    assert r_list.status_code == 200
    names = [x["name"] for x in r_list.json()]
    assert "Grade 7-X" in names

    # 4. Delete class
    r_del = c.delete(f"/api/classes/{cl_id}", headers=h)
    assert r_del.status_code == 200
    assert r_del.json()["deleted"] is True


def test_subjects_crud(client, auth):
    c, h = client, auth

    # 1. Create subject
    r = c.post("/api/subjects", headers=h, json={"name": "Social Studies", "code": "SOC-101"})
    assert r.status_code == 201, r.text
    sub_id = r.json()["id"]
    assert r.json()["name"] == "Social Studies"

    # 2. Update subject
    r_update = c.patch(f"/api/subjects/{sub_id}", headers=h, json={"name": "Social Science", "code": "SOC-102"})
    assert r_update.status_code == 200, r_update.text
    assert r_update.json()["name"] == "Social Science"
    assert r_update.json()["code"] == "SOC-102"

    # 3. Delete subject
    r_del = c.delete(f"/api/subjects/{sub_id}", headers=h)
    assert r_del.status_code == 200
    assert r_del.json()["deleted"] is True


def test_students_crud_and_name_update(client, auth):
    c, h = client, auth

    # Create temporary class
    r_cls = c.post("/api/classes", headers=h, json={"name": "Grade 9-A"})
    cl_id = r_cls.json()["id"]

    try:
        # 1. Create student
        r_st = c.post("/api/students", headers=h, json={"name": "Vikram", "roll_number": "55", "class_id": cl_id})
        assert r_st.status_code == 201, r_st.text
        st_id = r_st.json()["id"]
        assert r_st.json()["name"] == "Vikram"

        # 2. Update student name and roll number
        r_update = c.patch(f"/api/students/{st_id}", headers=h, json={"name": "Vikramaditya", "roll_number": "56"})
        assert r_update.status_code == 200, r_update.text
        assert r_update.json()["name"] == "Vikramaditya"
        assert r_update.json()["roll_number"] == "56"

        # 3. List students
        r_list = c.get(f"/api/students?class_id={cl_id}", headers=h)
        assert r_list.status_code == 200
        names = [s["name"] for s in r_list.json()]
        assert "Vikramaditya" in names

        # 4. Delete student
        r_del = c.delete(f"/api/students/{st_id}", headers=h)
        assert r_del.status_code == 200
        assert r_del.json()["deleted"] is True
    finally:
        c.delete(f"/api/classes/{cl_id}", headers=h)


def test_dynamic_marksheet_download_endpoint(client, auth):
    c, h = client, auth
    r = c.get("/api/reports/marksheet", headers=h)
    assert r.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in r.headers["content-type"]
    assert len(r.content) > 1000  # valid binary Excel workbook


def test_cascade_delete_class_and_subject_with_assigned_exams(client, auth):
    c, h = client, auth

    # 1. Create Class, Subject, Student, Exam
    cls = c.post("/api/classes", headers=h, json={"name": "Cascade Class 10"}).json()
    sub = c.post("/api/subjects", headers=h, json={"name": "Cascade Subject 10"}).json()
    st = c.post("/api/students", headers=h, json={
        "name": "Cascade Student", "roll_number": "999", "class_id": cls["id"]
    }).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "Cascade Exam", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 50
    }).json()

    # Verify exam exists
    assert c.get(f"/api/exams/{exam['id']}", headers=h).status_code == 200

    # 2. Deleting the class should cleanly cascade delete the exam, the student, and the class
    r_del_cls = c.delete(f"/api/classes/{cls['id']}", headers=h)
    assert r_del_cls.status_code == 200, r_del_cls.text
    assert r_del_cls.json()["deleted"] is True

    # Exam should be gone
    assert c.get(f"/api/exams/{exam['id']}", headers=h).status_code == 404
    # Student should be gone
    assert c.get(f"/api/students?class_id={cls['id']}", headers=h).json() == []

    # 3. Create another exam for subject, then delete subject
    cls2 = c.post("/api/classes", headers=h, json={"name": "Cascade Class 11"}).json()
    exam2 = c.post("/api/exams", headers=h, json={
        "name": "Cascade Exam 2", "academic_year": "2026-27",
        "class_id": cls2["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 50
    }).json()

    # Deleting the subject should cascade delete exam2 and subject
    r_del_sub = c.delete(f"/api/subjects/{sub['id']}", headers=h)
    assert r_del_sub.status_code == 200, r_del_sub.text
    assert r_del_sub.json()["deleted"] is True
    assert c.get(f"/api/exams/{exam2['id']}", headers=h).status_code == 404

    # Clean up cls2
    c.delete(f"/api/classes/{cls2['id']}", headers=h)



def test_class_is_std_plus_section(client, auth):
    c, h = client, auth
    r = c.post("/api/classes", headers=h, json={"std": " 11 ", "section": "1"})
    assert r.status_code == 201 and (r.json()["name"], r.json()["std"], r.json()["section"]) == ("11-1", "11", "1")
    nosec = c.post("/api/classes", headers=h, json={"std": "Grade 12"}).json()
    assert (nosec["name"], nosec["section"]) == ("Grade 12", None)
    old = c.post("/api/classes", headers=h, json={"name": "Grade 9-B"}).json()          # older clients still work
    assert (old["std"], old["section"]) == ("Grade 9", "B")
    upd = c.patch(f"/api/classes/{nosec['id']}", headers=h, json={"std": "Grade 12", "section": "Science"}).json()
    assert upd["name"] == "Grade 12-Science"
    assert c.post("/api/classes", headers=h, json={"section": "A"}).status_code == 400
