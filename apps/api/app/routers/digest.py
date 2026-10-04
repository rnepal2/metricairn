"""Weekly digest settings, preview, and manual send."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ApiKey, require_management_key, require_read_key
from app.models import DigestSetting
from app.services import digest as digest_svc

router = APIRouter(prefix="/api/v1/digest", tags=["digest"])


class DigestSettingIn(BaseModel):
    enabled: bool = True
    weekday: int = Field(default=0, ge=0, le=6)
    hour_utc: int = Field(default=12, ge=0, le=23)


def _out(s: DigestSetting) -> dict:
    return {
        "project_id": s.project_id,
        "enabled": s.enabled,
        "weekday": s.weekday,
        "hour_utc": s.hour_utc,
        "last_sent_at": s.last_sent_at.isoformat() if s.last_sent_at else None,
    }


@router.get("/settings")
def get_settings(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    s = db.query(DigestSetting).filter(DigestSetting.project_id == key.project_id).first()
    if not s:
        return {
            "project_id": key.project_id,
            "enabled": False,
            "weekday": 0,
            "hour_utc": 12,
            "last_sent_at": None,
        }
    return _out(s)


@router.put("/settings")
def put_settings(
    body: DigestSettingIn,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    s = db.query(DigestSetting).filter(DigestSetting.project_id == key.project_id).first()
    if not s:
        s = DigestSetting(project_id=key.project_id)
        db.add(s)
    s.enabled = body.enabled
    s.weekday = body.weekday
    s.hour_utc = body.hour_utc
    db.commit()
    db.refresh(s)
    return _out(s)


@router.post("/preview")
def preview(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    """See exactly what the next digest would say, without sending anything."""
    return digest_svc.compile_weekly(db, key.project_id)


@router.post("/send")
def send_now(key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)):
    """Compile and deliver the digest immediately (same path the scheduler uses)."""
    s = db.query(DigestSetting).filter(DigestSetting.project_id == key.project_id).first()
    if not s or not s.enabled:
        raise HTTPException(status_code=409, detail="Digest not enabled — configure settings first")
    return digest_svc.send_digest(db, key.project_id)
