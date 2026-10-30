"""Settings for printed documents: school details, report/report-card templates, and report card downloads."""
from __future__ import annotations
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err
from ..documents.storage import abs_path, data_root, read_validated_upload, rel, safe_join
from ..models import ReportTemplate, SchoolProfile, Student, Teacher
from ..security import current_teacher
from ..services.audit import audit
from ..services.report_templates import KINDS, active_template_id, list_presets, normalize, resolve, family_config
from ..services.school_reports import build_report_cards, render_preview, report_card_terms
from ..workspaces import owner_id

router = APIRouter(prefix="/api")


def _profile(db: Session, t: Teacher) -> SchoolProfile:
    p = db.query(SchoolProfile).filter_by(teacher_id=owner_id(db, t)).first()
    if p is None:
        p = SchoolProfile(teacher_id=owner_id(db, t))
        db.add(p)
        db.flush()
    return p


def _profile_view(p: SchoolProfile) -> dict:
    return {"name": p.name, "address": p.address, "principal_name": p.principal_name, "has_logo": bool(p.logo_file),
            "active_report_template": p.active_report_template, "active_card_template": p.active_card_template}


# ---------- school details
class ProfileIn(BaseModel):
    name: str = Field("", max_length=200)
    address: str = Field("", max_length=600)
    principal_name: str = Field("", max_length=200)


@router.get("/school-profile")
def get_school_profile(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    p = _profile(db, t)
    db.commit()
    return _profile_view(p)


@router.put("/school-profile")
def put_school_profile(body: ProfileIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    if not body.name.strip() or not body.address.strip():
        raise err(400, "SCHOOL_DETAILS_REQUIRED", "School name and address are required.")
    p = _profile(db, t)
    p.name, p.address, p.principal_name = body.name.strip(), body.address.strip(), body.principal_name.strip()
    from ..models import Workspace
    ws = db.get(Workspace, t.workspace_id)
    if ws:
        ws.name = p.name
    t.profile = {**(t.profile or {}), "school_name": p.name, "address": p.address, "principal_name": p.principal_name}
    db.commit()
    return _profile_view(p)


@router.post("/school-profile/logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    data, ext, _ = await read_validated_upload(file, {"png", "jpg", "jpeg"})
    if len(data) > 3 * 1024 * 1024:
        raise err(413, "FILE_TOO_LARGE", "The logo must be 3 MB or smaller.")
    p = _profile(db, t)
    d = safe_join(data_root(), "school", owner_id(db, t))
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("logo.*"):
        old.unlink()
    path = d / f"logo.{'jpg' if ext == 'jpeg' else ext}"
    path.write_bytes(data)
    p.logo_file = rel(path)
    db.commit()
    return _profile_view(p)


@router.delete("/school-profile/logo")
def delete_logo(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    p = _profile(db, t)
    if p.logo_file:
        f = abs_path(p.logo_file)
        if f.is_file():
            f.unlink()
        p.logo_file = None
    db.commit()
    return _profile_view(p)


@router.get("/school-profile/logo")
def get_logo(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    p = db.query(SchoolProfile).filter_by(teacher_id=owner_id(db, t)).first()
    f = abs_path(p.logo_file) if p and p.logo_file else None
    if f is None or not f.is_file():
        raise err(404, "NOT_FOUND", "No logo uploaded.")
    return FileResponse(f, media_type="image/png" if f.suffix == ".png" else "image/jpeg",
                        headers={"Cache-Control": "private, no-cache"})


# ---------- templates
def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise err(400, "INVALID_KIND", "Template kind must be 'report' or 'report_card'.")
    return kind


def _template(db: Session, t: Teacher, tid: str) -> ReportTemplate:
    row = db.get(ReportTemplate, tid)
    if row is None or row.teacher_id != owner_id(db, t):
        raise err(404, "NOT_FOUND", "Template not found.")
    return row


def _template_view(row: ReportTemplate) -> dict:
    return {"id": row.id, "name": row.name, "kind": row.kind, "preset": False, "config": normalize(row.kind, row.config)}


@router.get("/report-templates")
def list_templates(kind: str = Query(...), db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    kind = _kind(kind)
    p = _profile(db, t)
    db.commit()
    rows = db.query(ReportTemplate).filter_by(teacher_id=owner_id(db, t), kind=kind).order_by(ReportTemplate.created_at).all()
    return {"templates": list_presets(kind) + [_template_view(r) for r in rows], "active_id": active_template_id(p, kind)}


class TemplateIn(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=100)
    config: dict = {}


class TemplatePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict | None = None


@router.post("/report-templates", status_code=201)
def create_template(body: TemplateIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    kind = _kind(body.kind)
    row = ReportTemplate(teacher_id=owner_id(db, t), kind=kind, name=body.name.strip(), config=normalize(kind, body.config))
    db.add(row)
    db.flush()
    audit(db, exam_id=None, teacher_id=t.id, entity_type="report_template", entity_id=row.id, action="report_template_created",
          new=row.name)
    db.commit()
    return _template_view(row)


@router.put("/report-templates/{tid}")
def update_template(tid: str, body: TemplatePatch, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    row = _template(db, t, tid)
    if body.name is not None:
        row.name = body.name.strip()
    if body.config is not None:
        row.config = normalize(row.kind, body.config)
    db.commit()
    return _template_view(row)


@router.delete("/report-templates/{tid}")
def delete_template(tid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    row = _template(db, t, tid)
    p = _profile(db, t)
    # deleting the active template falls back to Classic
    if p.active_report_template == row.id:
        p.active_report_template = "preset:classic"
    if p.active_card_template == row.id:
        p.active_card_template = "preset:classic"
    db.delete(row)
    db.commit()
    return {"ok": True}


class ActivateIn(BaseModel):
    kind: str
    id: str


@router.post("/report-templates/activate")
def activate_template(body: ActivateIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    kind = _kind(body.kind)
    if not body.id.startswith("preset:"):
        if _template(db, t, body.id).kind != kind:
            raise err(400, "INVALID_KIND", "That template is for the other document.")
    elif body.id not in {x["id"] for x in list_presets(kind)}:
        raise err(404, "NOT_FOUND", "Template not found.")
    p = _profile(db, t)
    setattr(p, "active_report_template" if kind == "report" else "active_card_template", body.id)
    db.commit()
    return _profile_view(p)


class PreviewIn(BaseModel):
    kind: str
    config: dict = {}


def _pdf(pdf: bytes, filename: str, inline: bool = False) -> Response:
    disp = "inline" if inline else "attachment"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{filename}"', "Cache-Control": "private, no-cache"})


@router.post("/report-templates/preview")
def preview_draft(body: PreviewIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Sample-data PDF of an unsaved draft (the web editor's live preview)."""
    kind = _kind(body.kind)
    p = db.query(SchoolProfile).filter_by(teacher_id=owner_id(db, t)).first()
    cfg = normalize(kind, body.config)
    return _pdf(render_preview(kind, family_config(cfg) if t.role == "PARENT" else cfg, p), f"preview-{kind}.pdf", inline=True)


@router.get("/report-templates/{tid}/preview")
def preview_saved(tid: str, kind: str = Query(...), db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Sample-data PDF of a saved template or preset (used by the mobile editor)."""
    kind = _kind(kind)
    if not tid.startswith("preset:"):
        _template(db, t, tid)
    p = db.query(SchoolProfile).filter_by(teacher_id=owner_id(db, t)).first()
    cfg = resolve(db, t, kind, tid)
    return _pdf(render_preview(kind, family_config(cfg) if t.role == "PARENT" else cfg, p), f"preview-{kind}.pdf")


# ---------- report cards
@router.get("/classes/{class_id}/report-card-terms")
def card_terms(class_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    return report_card_terms(db, t, class_id)


@router.get("/classes/{class_id}/report-cards")
def class_report_cards(class_id: str, academic_year: str = Query(...), exam_type: str = Query(...),
                       db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    pdf, filename = build_report_cards(db, t, class_id, academic_year, exam_type)
    return _pdf(pdf, filename)


@router.get("/students/{student_id}/report-card")
def student_report_card(student_id: str, academic_year: str = Query(...), exam_type: str = Query(...),
                        db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    st = db.get(Student, student_id)
    if st is None:
        raise err(404, "NOT_FOUND", "Student not found.")
    pdf, filename = build_report_cards(db, t, st.class_id, academic_year, exam_type, student_id=st.id)
    return _pdf(pdf, filename)
