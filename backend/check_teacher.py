import httpx
from app.database import SessionLocal, init_db
from app.models import Teacher
from app.security import verify_password, hash_password

init_db()
db = SessionLocal()

# Ensure teacher@school.org exists with teacher123
t1 = db.query(Teacher).filter_by(email="teacher@school.org").first()
if not t1:
    db.add(Teacher(name="Demo Teacher", email="teacher@school.org", password_hash=hash_password("teacher123")))
    db.commit()
    print("Created teacher@school.org")

# Ensure you@school.org exists with a-strong-password
t2 = db.query(Teacher).filter_by(email="you@school.org").first()
if not t2:
    db.add(Teacher(name="School Teacher", email="you@school.org", password_hash=hash_password("a-strong-password")))
    db.commit()
    print("Created you@school.org")

# Test live API login
with httpx.Client(base_url="http://127.0.0.1:8000") as client:
    res1 = client.post("/api/auth/login", json={"email": "teacher@school.org", "password": "teacher123"})
    print("Login teacher@school.org:", res1.status_code, res1.json().get("teacher", {}).get("name"))

    res2 = client.post("/api/auth/login", json={"email": "you@school.org", "password": "a-strong-password"})
    print("Login you@school.org:", res2.status_code, res2.json().get("teacher", {}).get("name"))
