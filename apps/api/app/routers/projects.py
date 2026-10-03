"""Project provisioning, lookup, and timeline notes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import new_keypair, require_read_key, store_key
from app.models import ApiKey, Note, Project
from app.schemas import NoteCreate, ProjectCreate, ProjectOut

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name, domain=body.domain)
    db.add(project)
    db.commit()
    db.refresh(project)
    write_key, read_key = new_keypair()
    store_key(db, project_id=project.id, key=write_key, name="default-write", scopes="write")
    store_key(db, project_id=project.id, key=read_key, name="default-read", scopes="read")
    return ProjectOut(
        id=project.id,
        name=project.name,
        domain=project.domain,
        created_at=project.created_at,
        write_key=write_key,
        read_key=read_key,
    )


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [{"id": p.id, "name": p.name, "domain": p.domain} for p in projects]


@router.get("/me")
def whoami(key: ApiKey = Depends(require_read_key)):
    p = key.project
    return {"project_id": p.id, "name": p.name, "domain": p.domain}


@router.post("/{project_id}/notes")
def add_note(project_id: str, body: NoteCreate, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    _assert_key_project(key, project_id)
    note = Note(project_id=project_id, text=body.text, at=body.at)
    db.add(note)
    db.commit()
    return {"ok": True, "id": note.id}


@router.get("/{project_id}/notes")
def list_notes(project_id: str, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    _assert_key_project(key, project_id)
    notes = db.query(Note).filter(Note.project_id == project_id).order_by(Note.at.desc()).all()
    return [{"id": n.id, "text": n.text, "at": n.at.isoformat()} for n in notes]


def _assert_key_project(key: ApiKey, project_id: str) -> None:
    from fastapi import HTTPException

    if key.project_id != project_id:
        raise HTTPException(status_code=403, detail="Key does not belong to this project")
