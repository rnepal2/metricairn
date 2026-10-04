"""Anomaly alert engine: match detected anomalies against rules, respect
cooldowns, deliver to channels, and log every decision.

The scheduler (see app/main.py) calls check_all_projects() every 30 minutes.
The alerts router exposes the same logic for manual runs and testing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import AlertChannel, AlertDelivery, AlertRule, Project
from app.services import anomaly, notify

# Built-in rule applied when a project has channels but no enabled rules.
DEFAULT_RULE = {
    "id": "",
    "name": "Default: any significant anomaly",
    "metric": "any",
    "direction": "any",
    "min_z": 3.0,
    "cooldown_hours": 24.0,
}

CHECK_WINDOW_DAYS = 3  # only anomalies in the last N days are alertable


def anomaly_key(a: dict) -> str:
    key = f"{a['metric']}:{a['direction']}:{a['date']}"
    if a.get("date_end"):
        key += f":{a['date_end']}"
    return key


def rule_matches(a: dict, rule: dict) -> bool:
    if rule["metric"] != "any" and a["metric"] != rule["metric"]:
        return False
    if rule["direction"] != "any" and a["direction"] != rule["direction"]:
        return False
    return abs(a["z_score"]) >= rule["min_z"]


def _cooldown_ok(db: Session, project_id: str, channel_id: str, key: str, hours: float) -> bool:
    """True if no 'sent' delivery for this anomaly key within the cooldown."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    hit = (
        db.query(AlertDelivery)
        .filter(
            AlertDelivery.project_id == project_id,
            AlertDelivery.channel_id == channel_id,
            AlertDelivery.anomaly_key == key,
            AlertDelivery.status == "sent",
            AlertDelivery.created_at >= since,
        )
        .first()
    )
    return hit is None


def log_delivery(
    db: Session,
    project_id: str,
    channel_id: str,
    rule_id: str,
    key: str,
    status: str,
    detail: str,
) -> None:
    db.add(
        AlertDelivery(
            project_id=project_id,
            channel_id=channel_id,
            rule_id=rule_id,
            anomaly_key=key,
            status=status,
            detail=detail[:500],
        )
    )
    db.commit()


def check_project(db: Session, project_id: str) -> dict:
    """Run one alert cycle for a project. Returns a summary of decisions."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"project_id": project_id, "checked": False, "reason": "no such project"}

    channels = (
        db.query(AlertChannel)
        .filter(AlertChannel.project_id == project_id, AlertChannel.enabled.is_(True))
        .all()
    )
    if not channels:
        return {"project_id": project_id, "checked": False, "reason": "no enabled channels"}

    rules = (
        db.query(AlertRule)
        .filter(AlertRule.project_id == project_id, AlertRule.enabled.is_(True))
        .all()
    )
    rule_dicts = (
        [
            {
                "id": r.id,
                "name": r.name,
                "metric": r.metric,
                "direction": r.direction,
                "min_z": r.min_z,
                "cooldown_hours": r.cooldown_hours,
            }
            for r in rules
        ]
        if rules
        else [DEFAULT_RULE]
    )

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=CHECK_WINDOW_DAYS)
    anomalies = anomaly.detect(db, project_id, start, now)
    # Only fresh anomalies: skip anything whose window ended more than a day ago
    # (prevents re-alerting on old news after a scheduler outage).
    fresh = []
    for a in anomalies:
        end_day = datetime.fromisoformat(a.get("date_end") or a["date"]).replace(
            tzinfo=timezone.utc
        )
        if (now - end_day).days <= 1:
            fresh.append(a)

    summary = {"project_id": project_id, "checked": True, "sent": 0, "skipped": 0, "failed": 0}
    for channel in channels:
        for rule in rule_dicts:
            group = [a for a in fresh if rule_matches(a, rule)]
            if not group:
                continue
            keys = sorted({anomaly_key(a) for a in group})
            # Per-key cooldown: only alert on anomalies not already notified
            # for this channel inside the rule's cooldown window.
            fresh_keys = [
                k
                for k in keys
                if _cooldown_ok(db, project_id, channel.id, k, rule["cooldown_hours"])
            ]
            for k in keys:
                if k not in fresh_keys:
                    log_delivery(db, project_id, channel.id, rule["id"], k, "skipped", "cooldown")
                    summary["skipped"] += 1
            if not fresh_keys:
                continue
            fresh_anomalies = [a for a in group if anomaly_key(a) in set(fresh_keys)]
            subject, body = notify.format_anomaly_message(project.name, fresh_anomalies)
            ok, detail = notify.deliver(channel.kind, channel.target, subject, body)
            for k in fresh_keys:
                log_delivery(
                    db, project_id, channel.id, rule["id"], k,
                    "sent" if ok else "failed", detail,
                )
            summary["sent" if ok else "failed"] += 1
    return summary


def check_all_projects() -> list[dict]:
    """Scheduler entrypoint: check every project that has enabled channels."""
    db = SessionLocal()
    try:
        project_ids = [
            c.project_id
            for c in db.query(AlertChannel.project_id)
            .filter(AlertChannel.enabled.is_(True))
            .distinct()
            .all()
        ]
        return [check_project(db, pid) for pid in project_ids]
    finally:
        db.close()
