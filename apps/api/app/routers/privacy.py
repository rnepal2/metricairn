"""Data transparency and deletion.

AgentLens only ever sees the events a customer explicitly sends us — this
router makes that verifiable: what we hold for a project, and a one-click
way to remove all of it. Deleting data keeps the project and its API keys;
it removes every row derived from customer activity.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_read_key, require_write_key
from app.models import (
    AlertChannel,
    AlertDelivery,
    AlertRule,
    ApiKey,
    DigestSetting,
    Event,
    Funnel,
    Note,
)
from app.routers.projects import _assert_key_project

router = APIRouter(prefix="/api/v1/projects", tags=["privacy"])

# Every table whose rows are derived from customer activity. ApiKey and
# Project are deliberately excluded: deleting data must not lock the
# customer out or destroy their keys.
_DELETABLE = [
    (Event, "events"),
    (Note, "notes"),
    (Funnel, "funnels"),
    (AlertChannel, "alert_channels"),
    (AlertRule, "alert_rules"),
    (AlertDelivery, "alert_deliveries"),
    (DigestSetting, "digest_settings"),
]


@router.get("/{project_id}/data/summary")
def data_summary(
    project_id: str,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    """What AgentLens currently holds for this project — counts, date range,
    and the event names flowing in. The transparency counterpart to DELETE."""
    _assert_key_project(key, project_id)

    first = (
        db.query(func.min(Event.created_at))
        .filter(Event.project_id == project_id)
        .scalar()
    )
    last = (
        db.query(func.max(Event.created_at))
        .filter(Event.project_id == project_id)
        .scalar()
    )
    top_events = (
        db.query(Event.name, func.count(Event.id).label("n"))
        .filter(Event.project_id == project_id)
        .group_by(Event.name)
        .order_by(func.count(Event.id).desc())
        .limit(10)
        .all()
    )
    revenue_events = (
        db.query(func.count(Event.id))
        .filter(Event.project_id == project_id, Event.name == "revenue")
        .scalar()
    )
    return {
        "project_id": project_id,
        "events": db.query(func.count(Event.id)).filter(Event.project_id == project_id).scalar(),
        "notes": db.query(func.count(Note.id)).filter(Note.project_id == project_id).scalar(),
        "funnels": db.query(func.count(Funnel.id)).filter(Funnel.project_id == project_id).scalar(),
        "revenue_events": revenue_events,
        "first_event_at": first.isoformat() if first else None,
        "last_event_at": last.isoformat() if last else None,
        "top_events": [{"name": name, "count": n} for name, n in top_events],
    }


@router.delete("/{project_id}/data")
def delete_all_data(
    project_id: str,
    key: ApiKey = Depends(require_write_key),
    db: Session = Depends(get_db),
):
    """Remove everything AgentLens holds for this project: events, notes,
    funnels, alert configuration and delivery history. Requires the write
    key — a read key (or the dashboard alone) can never do this."""
    _assert_key_project(key, project_id)
    deleted: dict[str, int] = {}
    for model, label in _DELETABLE:
        deleted[label] = (
            db.query(model).filter(model.project_id == project_id).delete(synchronize_session=False)
        )
    db.commit()
    return {"ok": True, "deleted": deleted}
