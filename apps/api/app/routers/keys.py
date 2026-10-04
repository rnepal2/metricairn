"""Project-scoped key inventory, issuance and revocation for private managers."""

import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_management_key, store_key
from app.models import ApiKey

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


class KeyCreate(BaseModel):
    kind: Literal["read", "tracking", "management"]
    name: str = Field(min_length=1, max_length=200)


def metadata(record):
    return {
        "id": record.id,
        "name": record.name,
        "prefix": record.key_prefix,
        "scopes": record.scopes,
        "revoked": record.revoked,
        "created_at": record.created_at,
    }


@router.get("")
def list_keys(key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)):
    return [
        metadata(record)
        for record in db.query(ApiKey)
        .filter(ApiKey.project_id == key.project_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    ]


@router.post("")
def issue_key(
    body: KeyCreate, key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)
):
    prefix, scope = {
        "read": ("alr", "read"),
        "tracking": ("alw", "write"),
        "management": ("alm", "manage"),
    }[body.kind]
    raw = f"{prefix}_{secrets.token_urlsafe(32)}"
    record = store_key(db, project_id=key.project_id, key=raw, name=body.name, scopes=scope)
    return {**metadata(record), "key": raw}


@router.delete("/{key_id}")
def revoke_key(
    key_id: str, key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)
):
    record = (
        db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.project_id == key.project_id).first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Key not found")
    # Keep managers from accidentally locking themselves out of their project.
    if record.id == key.id:
        raise HTTPException(
            status_code=409,
            detail="Cannot revoke your current management key. Connect with its replacement first.",
        )
    record.revoked = True
    db.commit()
    return {"ok": True}
