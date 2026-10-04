"""Deterministic exploration and project-scoped evidence records."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_management_key, require_read_key
from app.models import ApiKey, Goal, Investigation
from app.services.analytics import SYSTEM_EVENTS, parse_range
from app.services.exploration import QueryPlan, goal_report, investigate, retention, run_plan

router = APIRouter(prefix="/api/v1", tags=["exploration"])


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    event_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def customer_event(self):
        if self.event_name in (*SYSTEM_EVENTS, "pageview", "revenue"):
            raise ValueError("Choose a custom product event, such as signup or activation")
        return self


class SaveInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    plan: QueryPlan


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["observed", "investigating", "resolved", "dismissed"]
    note: str = Field(default="", max_length=2000)


def scoped(db, model, identity, project_id):
    row = db.query(model).filter(model.id == identity, model.project_id == project_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    return row


def summary(item):
    return {
        "id": item.id,
        "title": item.title,
        "status": item.status,
        "review_note": item.review_note,
        "reviewed_at": item.reviewed_at,
        "created_at": item.created_at,
        "evidence_id": item.evidence["evidence_id"],
    }


@router.post("/query/run")
def query_plan(
    body: QueryPlan, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)
):
    return run_plan(db, key.project_id, body)


@router.get("/goals")
def goals(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    return [
        {"id": row.id, "name": row.name, "event_name": row.event_name}
        for row in db.query(Goal)
        .filter(Goal.project_id == key.project_id)
        .order_by(Goal.created_at, Goal.id)
        .all()
    ]


@router.post("/goals", status_code=201)
def create_goal(
    body: GoalCreate, key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)
):
    row = Goal(project_id=key.project_id, **body.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "event_name": row.event_name}


@router.delete("/goals/{goal_id}")
def delete_goal(
    goal_id: str, key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)
):
    row = scoped(db, Goal, goal_id, key.project_id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/goals/{goal_id}/report")
def report_goal(
    goal_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    goal = scoped(db, Goal, goal_id, key.project_id)
    return goal_report(db, key.project_id, goal, *parse_range(date_from, date_to))


@router.get("/query/retention")
def report_retention(
    date_from: str | None = None,
    date_to: str | None = None,
    event_name: str | None = Query(default=None, min_length=1, max_length=200),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    return retention(db, key.project_id, *parse_range(date_from, date_to), event_name)


@router.post("/investigations/run")
def run_investigation(
    body: QueryPlan, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)
):
    return investigate(db, key.project_id, body)


@router.get("/investigations")
def investigations(
    limit: int = Query(default=30, ge=1, le=100),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    return [
        summary(row)
        for row in db.query(Investigation)
        .filter(Investigation.project_id == key.project_id)
        .order_by(Investigation.created_at.desc(), Investigation.id)
        .limit(limit)
        .all()
    ]


@router.post("/investigations", status_code=201)
def save_investigation(
    body: SaveInvestigation,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    report = investigate(db, key.project_id, body.plan)
    row = Investigation(project_id=key.project_id, title=body.title, evidence=report)
    db.add(row)
    db.commit()
    return summary(row) | {"evidence": report}


@router.get("/investigations/{investigation_id}")
def read_investigation(
    investigation_id: str, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)
):
    row = scoped(db, Investigation, investigation_id, key.project_id)
    return summary(row) | {"evidence": row.evidence}


@router.patch("/investigations/{investigation_id}")
def review_investigation(
    investigation_id: str,
    body: Review,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    row = scoped(db, Investigation, investigation_id, key.project_id)
    row.status, row.review_note = body.status, body.note
    row.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return summary(row) | {"evidence": row.evidence}
