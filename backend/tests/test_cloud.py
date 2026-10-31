from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import create_engine, inspect, text
from app.config import get_settings
from app.database import SessionLocal, Base
from app.documents import cloud
from app.documents.storage import abs_path, rel
from app.models import BackgroundJob, PendingUpload, Teacher, Workspace
from app.ocr import remote, internvl
from app.ocr.schemas import QuestionPageResult
from app.security import create_token
from tests.conftest import make_pdf


@pytest.fixture
def private_storage(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "https://storage.example.test")
    monkeypatch.setattr(settings, "supabase_service_role_key", "private-test-key")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "papers")
    objects, requests = {}, []
    cloud._uploaded.clear()
    def request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        assert kwargs["headers"]["apikey"] == "private-test-key"
        path = httpx.URL(url).path.removeprefix("/storage/v1")
        data, status = {}, 200
        if path == "/bucket/papers":
            data = {"public": False}
        elif path.startswith("/object/upload/sign/papers/"):
            data = {"url": path + "?token=one-object-only"}
        elif method == "POST" and path == "/object/list/papers":
            prefix = kwargs["json"]["prefix"].rstrip("/") + "/"
            children = {}
            for key in objects:
                if key.startswith(prefix):
                    rest = key[len(prefix):]
                    name = rest.split("/")[0]
                    children[name] = {"name": name, "id": None if "/" in rest else name}
            offset = kwargs["json"].get("offset", 0)
            data = sorted(children.values(), key=lambda r: r["name"])[offset:offset+100]
        elif method == "POST" and path.startswith("/object/papers/"):
            objects[path.removeprefix("/object/papers/")] = kwargs["content"]
        elif method == "GET" and path.startswith("/object/authenticated/papers/"):
            key = path.removeprefix("/object/authenticated/papers/")
            if key in objects:
                return httpx.Response(200, content=objects[key], request=httpx.Request(method,url))
            status, data = 404, {"statusCode": "404"}
        elif method == "DELETE" and path == "/object/papers":
            for key in kwargs["json"]["prefixes"]:
                objects.pop(key, None)
        else:
            raise AssertionError((method, path))
        return httpx.Response(status, json=data, request=httpx.Request(method,url))
    monkeypatch.setattr(cloud.httpx, "request", request)
    yield objects, requests
    cloud._uploaded.clear()


def test_storage_cache_hydration_and_cloud_retention(client, private_storage):
    objects, requests = private_storage
    path = get_settings().data_path / "exams/cloud-test/original.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"private paper")
    key = rel(path)
    assert objects[key] == b"private paper"
    path.unlink()
    assert abs_path(key).read_bytes() == b"private paper"
    objects["exams/cloud-test/reports/report.pdf"] = b"retained"
    cloud.remove_prefix("exams/cloud-test", keep_reports=True)
    assert key not in objects and objects["exams/cloud-test/reports/report.pdf"] == b"retained"
    for invalid in ("../secret", "/absolute", ".secret_key", "C:\\secret", "folder/../../secret"):
        with pytest.raises(cloud.StorageError):
            cloud.key_for(invalid)


def test_signed_upload_completion_is_authorized_validated_and_idempotent(client, auth, private_storage):
    objects, _ = private_storage
    cls = client.post("/api/classes", headers=auth, json={"std":"10","section":"Cloud"}).json()
    subject = client.post("/api/subjects", headers=auth, json={"name":"Cloud English"}).json()
    exam = client.post("/api/exams", headers=auth, json={"name":"Cloud exam","class_id":cls["id"],"subject_id":subject["id"],"exam_type":"Unit","total_marks":7}).json()
    content = make_pdf()
    lease = client.post(f"/api/exams/{exam['id']}/uploads", headers=auth, json={"kind":"question-paper","filename":"paper.pdf","file_size":len(content)})
    assert lease.status_code == 201, lease.text
    assert "private-test-key" not in lease.text
    uid = lease.json()["id"]
    with SessionLocal() as db:
        row = db.get(PendingUpload, uid)
        objects[row.object_key] = b"not the announced file"
        other = Teacher(name="Other",email=f"{uuid4().hex}@example.com",role="MANAGEMENT",password_hash="!unused",profile_completed_at=datetime.now(timezone.utc))
        db.add(other); db.flush()
        ws = Workspace(name="Other school",kind="SCHOOL",owner_id=other.id)
        db.add(ws); db.flush(); other.workspace_id=ws.id;db.commit()
        other_auth={"Authorization":"Bearer "+create_token(other.id)}
        key=row.object_key
    assert client.post(f"/api/uploads/{uid}/complete", headers=other_auth).status_code == 404
    assert client.post(f"/api/uploads/{uid}/complete", headers=auth).status_code == 400
    objects[key] = content
    first = client.post(f"/api/uploads/{uid}/complete", headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["id"] == uid
    assert client.post(f"/api/uploads/{uid}/complete", headers=auth).json() == first.json()
    document = client.get(f"/api/exams/{exam['id']}/question-paper", headers=auth).json()
    assert document["status"] == "READY"
    assert key not in objects
    with SessionLocal() as db:
        from app.models import QuestionPaperDocument
        original = db.get(QuestionPaperDocument, uid).original_file
    abs_path(original).unlink()
    assert client.get(f"/api/documents/question-paper/{uid}/pdf", headers=auth).status_code == 200


def test_remote_ai_transport_and_unmeasured_confidence(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings,"ai_provider","openrouter")
    monkeypatch.setattr(settings,"openrouter_api_key","private-ai-key")
    monkeypatch.setattr(settings,"openrouter_model","qwen/qwen3-vl-8b-instruct")
    image=tmp_path/"page.png";image.write_bytes(b"test image")
    captured={}
    raw='{"questions":[{"raw_question_number":"1","question_text":"A question","marks":2,"confidence":0.99}]}'
    def post(url,**kwargs):
        captured.update(kwargs)
        return httpx.Response(200,json={"choices":[{"message":{"content":raw},"finish_reason":"stop"}]},request=httpx.Request("POST",url))
    monkeypatch.setattr(remote.httpx,"post",post)
    result=internvl.chat_structured("system","read",QuestionPageResult,image)
    assert captured["headers"]["Authorization"] == "Bearer private-ai-key"
    assert captured["json"]["model"] == settings.openrouter_model
    assert captured["json"]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert result.parsed.questions[0].confidence <= 0.5
    monkeypatch.setattr(settings,"ai_provider","custom")
    monkeypatch.setattr(settings,"custom_ai_base_url","https://private-model.example/v1")
    monkeypatch.setattr(settings,"custom_ai_api_key","endpoint-key")
    monkeypatch.setattr(settings,"custom_ai_model","private-vlm")
    internvl.chat_structured("system","read",QuestionPageResult)
    assert captured["json"]["model"] == "private-vlm"
    assert captured["headers"]["Authorization"] == "Bearer endpoint-key"


def test_versioned_migrations_are_repeatable(tmp_path):
    from alembic import command
    from alembic.config import Config
    engine=create_engine(f"sqlite:///{tmp_path/'schema.db'}")
    config=Config(str(Path(__file__).resolve().parents[1]/"alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"]=connection
        command.upgrade(config,"head"); command.upgrade(config,"head")
        assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "20261030_uploads"


def test_durable_queue_deduplicates_recovers_queued_and_flags_interrupted(client, auth, monkeypatch):
    from app.services import persistent_queue as pq, job_queue as jq
    from app.services.pipeline import process_document
    monkeypatch.setattr(jq,"_waiting",[])
    monkeypatch.setattr(jq,"_scheduled",set())
    monkeypatch.setattr(jq,"_ensure_workers",lambda:None)
    cls=client.post('/api/classes',headers=auth,json={'std':'12','section':'Durable'}).json()
    sub=client.post('/api/subjects',headers=auth,json={'name':'Durable English'}).json()
    exam=client.post('/api/exams',headers=auth,json={'name':'Durable','class_id':cls['id'],'subject_id':sub['id'],'exam_type':'Unit','total_marks':2}).json()
    job=jq._Job('internvl',process_document,('question-paper','document-id'),exam_id=exam['id'])
    job_id=pq.persist(job)
    assert job_id and pq.persist(job) is None
    pq.restore_queued();pq.restore_queued()
    assert len([j for j in jq._waiting if j.job_id==job_id])==1
    assert pq.claim(job_id) and not pq.claim(job_id)
    with SessionLocal() as db:
        assert exam['id'] in pq.protected_exams(db)
        row=db.get(BackgroundJob,job_id)
        row.heartbeat_at=datetime.now(timezone.utc)-timedelta(minutes=5)
        db.commit()
    pq.recover_stale()
    with SessionLocal() as db:
        row=db.get(BackgroundJob,job_id)
        assert row.status=='INTERRUPTED' and row.active_key is None
        assert exam['id'] not in pq.protected_exams(db)
    # Interrupted jobs are not automatically rerun and charged again.
    monkeypatch.setattr(jq,'_waiting',[]);monkeypatch.setattr(jq,'_scheduled',set())
    pq.restore_queued()
    assert not jq._waiting
