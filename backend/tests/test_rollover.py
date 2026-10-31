"""Year rollover: students are copied into next year's class (last year's class is untouched), a rerun copies no one
twice, Class 12 graduates, and only the School Manager can do it."""
import uuid


def test_rollover_copies_students_once_and_keeps_last_year(client, auth, teach):
    sec = uuid.uuid4().hex[:4].upper()
    old = client.post("/api/classes", headers=auth, json={"std": "10", "section": sec}).json()
    leaving = client.post("/api/classes", headers=auth, json={"std": "12", "section": sec}).json()
    for i in range(3):
        assert client.post("/api/students", headers=auth,
                           json={"name": f"S{i}", "roll_number": str(i + 1), "class_id": old["id"]}).status_code == 201
    body = {"academic_year": "2027-28", "moves": [
        {"from_class_id": old["id"], "to_class_name": f"10-{sec}N"},
        {"from_class_id": leaving["id"], "graduate": True}]}
    preview = client.post("/api/school/rollover", headers=auth, json={**body, "dry_run": True}).json()
    assert preview["moves"][0]["copied"] == 3
    assert not any(c["name"] == f"10-{sec}N" for c in client.get("/api/classes", headers=auth).json())
    done = client.post("/api/school/rollover", headers=auth, json=body).json()
    assert done["moves"][0] == {"from": f"10-{sec}", "to": f"10-{sec}N", "created": True, "copied": 3, "skipped": 0}
    again = client.post("/api/school/rollover", headers=auth, json=body).json()
    assert again["moves"][0]["copied"] == 0 and again["moves"][0]["skipped"] == 3
    assert len(client.get(f"/api/students?class_id={old['id']}", headers=auth).json()) == 3
    assert client.post("/api/school/rollover", headers=auth, json={"academic_year": "2027-28", "moves": [
        {"from_class_id": old["id"], "to_class_name": "11-A"}]}).json()["code"] == "CBSE_CLASS_REQUIRED"
    assert client.post("/api/school/rollover", headers=teach, json=body).status_code == 403
