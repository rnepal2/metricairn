"""Alert channels, rules, delivery log, and manual check/test triggers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ApiKey, require_management_key, require_read_key
from app.models import AlertChannel, AlertDelivery, AlertRule
from app.schemas import (
    AlertChannelCreate,
    AlertChannelOut,
    AlertDeliveryOut,
    AlertRuleCreate,
    AlertRuleOut,
)
from app.services import alerting, notify

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _channel_out(c: AlertChannel) -> dict:
    return {
        "id": c.id,
        "kind": c.kind,
        # Webhook URLs are bearer secrets; read keys must never see any part
        # of one. Email addresses are safe to display.
        "target": c.target if c.kind == "email" else "••••••",
        "enabled": c.enabled,
        "created_at": c.created_at,
    }


@router.post("/channels", response_model=AlertChannelOut)
def create_channel(
    body: AlertChannelCreate,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    if body.kind == "email" and "@" not in body.target:
        raise HTTPException(status_code=422, detail="Not a valid email address")
    if body.kind == "slack" and not body.target.startswith("https://hooks.slack.com/"):
        raise HTTPException(status_code=422, detail="Not a Slack webhook URL")
    c = AlertChannel(project_id=key.project_id, kind=body.kind, target=body.target)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _channel_out(c)


@router.get("/channels", response_model=list[AlertChannelOut])
def list_channels(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    channels = (
        db.query(AlertChannel)
        .filter(AlertChannel.project_id == key.project_id)
        .order_by(AlertChannel.created_at.desc())
        .all()
    )
    return [_channel_out(c) for c in channels]


@router.delete("/channels/{channel_id}")
def delete_channel(
    channel_id: str,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    c = (
        db.query(AlertChannel)
        .filter(AlertChannel.id == channel_id, AlertChannel.project_id == key.project_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/channels/{channel_id}/test")
def test_channel(
    channel_id: str,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    c = (
        db.query(AlertChannel)
        .filter(AlertChannel.id == channel_id, AlertChannel.project_id == key.project_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Channel not found")
    subject, body = notify.format_anomaly_message(key.project.name, [], test=True)
    ok, detail = notify.deliver(c.kind, c.target, subject, body)
    alerting.log_delivery(db, key.project_id, c.id, "", "test", "sent" if ok else "failed", detail)
    return {"ok": ok, "detail": detail}


@router.post("/rules", response_model=AlertRuleOut)
def create_rule(
    body: AlertRuleCreate,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    r = AlertRule(
        project_id=key.project_id,
        name=body.name,
        metric=body.metric,
        direction=body.direction,
        min_z=body.min_z,
        cooldown_hours=body.cooldown_hours,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {
        "id": r.id,
        "name": r.name,
        "metric": r.metric,
        "direction": r.direction,
        "min_z": r.min_z,
        "cooldown_hours": r.cooldown_hours,
        "enabled": r.enabled,
        "created_at": r.created_at,
    }


@router.get("/rules", response_model=list[AlertRuleOut])
def list_rules(key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.project_id == key.project_id)
        .order_by(AlertRule.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "metric": r.metric,
            "direction": r.direction,
            "min_z": r.min_z,
            "cooldown_hours": r.cooldown_hours,
            "enabled": r.enabled,
            "created_at": r.created_at,
        }
        for r in rules
    ]


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: str,
    key: ApiKey = Depends(require_management_key),
    db: Session = Depends(get_db),
):
    r = (
        db.query(AlertRule)
        .filter(AlertRule.id == rule_id, AlertRule.project_id == key.project_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/deliveries", response_model=list[AlertDeliveryOut])
def list_deliveries(
    limit: int = 50,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AlertDelivery)
        .filter(AlertDelivery.project_id == key.project_id)
        .order_by(AlertDelivery.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": d.id,
            "channel_id": d.channel_id,
            "rule_id": d.rule_id,
            "anomaly_key": d.anomaly_key,
            "status": d.status,
            "detail": d.detail,
            "created_at": d.created_at,
        }
        for d in rows
    ]


@router.post("/check")
def run_check(key: ApiKey = Depends(require_management_key), db: Session = Depends(get_db)):
    """Manually trigger one alert cycle for the key's project (same logic the
    scheduler runs every 30 minutes)."""
    return alerting.check_project(db, key.project_id)
