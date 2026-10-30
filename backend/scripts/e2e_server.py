"""Isolated browser-test server. Never used by the production image entrypoint."""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="eval-browser-test-")
os.environ["ENVIRONMENT"] = "development"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SECRET_KEY"] = "browser-test-secret-only-not-for-production"
os.environ["INTERNVL_ENABLED"] = "false"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:4174"
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""

from app.database import SessionLocal, init_db
from app.models import Teacher, Workspace
from datetime import datetime, timezone
from app.security import hash_password
import uvicorn

if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        user = Teacher(name="Browser Test", email="browser@example.test", role="MANAGEMENT", profile_completed_at=datetime.now(timezone.utc), password_hash=hash_password("test-password-123"))
        db.add(user)
        db.flush()
        workspace = Workspace(name="Browser School", kind="SCHOOL", owner_id=user.id)
        db.add(workspace)
        db.flush()
        user.workspace_id = workspace.id
        db.add(Teacher(name="Owner", email="seyamesh91@gmail.com", password_hash=hash_password("owner-test-password-123")))
        db.commit()
    uvicorn.run("app.main:app", host="127.0.0.1", port=18000)
