"""Funnels: define ordered page/event sequences, get conversion reports."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_management_key, require_read_key
from app.models import ApiKey, Funnel
from app.schemas import FunnelCreate
from app.services import analytics
from app.services.analytics import parse_range

router = APIRouter(prefix="/api/v1/funnels", tags=["funnels"])


@router.post("")
def create_funnel(
    body: FunnelCreate, key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)
):
    for step in body.steps:
        if step.get("kind") not in ("page", "event") or not step.get("value"):
            raise HTTPException(
                status_code=422, detail="Each step needs {kind: page|event, value: str}"
            )
    funnel = Funnel(project_id=key.project_id, name=body.name, steps=body.steps)
    db.add(funnel)
    db.commit()
    db.refresh(funnel)
    return {"id": funnel.id, "name": funnel.name, "steps": funnel.steps}


@router.get("")
def list_funnels(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    funnels = db.query(Funnel).filter(Funnel.project_id == key.project_id).all()
    return [{"id": f.id, "name": f.name, "steps": f.steps} for f in funnels]


@router.get("/{funnel_id}/report")
def funnel_report(
    funnel_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    segment_by: str | None = None,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    funnel = (
        db.query(Funnel).filter(Funnel.id == funnel_id, Funnel.project_id == key.project_id).first()
    )
    if not funnel:
        raise HTTPException(status_code=404, detail="Funnel not found")
    start, end = parse_range(date_from, date_to)
    steps = analytics.funnel_report(db, key.project_id, funnel.steps, start, end)
    overall = steps[-1]["conversion_from_start"] if steps else 0.0
    out = {
        "funnel_id": funnel.id,
        "name": funnel.name,
        "steps": steps,
        "overall_conversion": overall,
    }
    if segment_by:
        try:
            out["segments"] = analytics.funnel_report_by_segment(
                db, key.project_id, funnel.steps, start, end, segment_by
            )
            out["segment_by"] = segment_by
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    return out
