"""Project provisioning, lookup, and timeline notes."""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import new_keypair, require_management_key, require_read_key, store_key
from app.models import ApiKey, Note, Project
from app.schemas import NoteCreate, ProjectCreate, ProjectOut

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    x_provisioning_token: str | None = Header(default=None),
):
    settings = get_settings()
    if settings.provisioning_token and not secrets.compare_digest(
        (x_provisioning_token or "").encode(), settings.provisioning_token.encode()
    ):
        raise HTTPException(
            status_code=403, detail="Project creation requires a provisioning token"
        )
    project = Project(name=body.name, domain=body.domain)
    db.add(project)
    db.commit()
    db.refresh(project)
    write_key, read_key = new_keypair()
    store_key(db, project_id=project.id, key=write_key, name="default-write", scopes="write")
    store_key(db, project_id=project.id, key=read_key, name="default-read", scopes="read")
    management_key = f"alm_{secrets.token_urlsafe(32)}"
    store_key(
        db, project_id=project.id, key=management_key, name="default-management", scopes="manage"
    )
    return ProjectOut(
        id=project.id,
        name=project.name,
        domain=project.domain,
        created_at=project.created_at,
        write_key=write_key,
        read_key=read_key,
        management_key=management_key,
    )


@router.get("")
def list_projects(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.id == key.project_id).all()
    return [{"id": p.id, "name": p.name, "domain": p.domain} for p in projects]


@router.get("/me")
def whoami(key: ApiKey = Depends(require_read_key)):
    p = key.project
    return {"project_id": p.id, "name": p.name, "domain": p.domain}


@router.post("/{project_id}/notes")
def add_note(
    project_id: str,
    body: NoteCreate,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    _assert_key_project(key, project_id)
    note = Note(project_id=project_id, text=body.text, at=body.at)
    db.add(note)
    db.commit()
    return {"ok": True, "id": note.id}


@router.get("/{project_id}/notes")
def list_notes(
    project_id: str, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)
):
    _assert_key_project(key, project_id)
    notes = db.query(Note).filter(Note.project_id == project_id).order_by(Note.at.desc()).all()
    return [{"id": n.id, "text": n.text, "at": n.at.isoformat()} for n in notes]


def _assert_key_project(key: ApiKey, project_id: str) -> None:
    from fastapi import HTTPException

    if key.project_id != project_id:
        raise HTTPException(status_code=403, detail="Key does not belong to this project")


@router.get("/{project_id}/management")
def verify_management(project_id: str, key: ApiKey = Depends(require_management_key)):
    _assert_key_project(key, project_id)
    return {"ok": True, "project_id": project_id}
