"""Weekly founder digest: the week's numbers compiled into one message and
delivered to the project's alert channels.

The digest answers the question a solo founder actually asks on Monday
morning — "anything I need to know?" — without opening a dashboard. Content
is factual (numbers + WoW deltas); interpretation is left to the ask endpoint
and the agent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import AlertChannel, DigestSetting, Funnel, Project
from app.services import analytics, anomaly, notify


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; treat them as UTC.
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _wow(cur: float, prev: float) -> str:
    if not prev:
        return "n/a" if not cur else "new"
    pct = (cur - prev) / prev * 100
    return f"{pct:+.0f}%"


def _money(v: float) -> str:
    return f"${v:,.0f}"


def compile_weekly(db: Session, project_id: str, end: datetime | None = None) -> dict:
    """Compile the digest for the 7 days ending at `end` (default now)."""
    now = _aware(end) or datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)

    cur = analytics.overview(db, project_id, week_start, now)
    prev = analytics.overview(db, project_id, prev_start, week_start)

    anomalies = anomaly.detect(db, project_id, week_start, now)

    camps = analytics.breakdown(db, project_id, "utm_campaign", week_start, now, limit=50)
    top_camps = sorted(
        [(r["value"], r["revenue"]) for r in camps if r["value"] != "(not set)" and r["revenue"] > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    funnel_line = None
    funnel = db.query(Funnel).filter(Funnel.project_id == project_id).order_by(Funnel.created_at).first()
    if funnel and funnel.steps:
        rep = analytics.funnel_report(db, project_id, funnel.steps, week_start, now)
        if rep and rep[0]["visitors"]:
            conv = rep[-1]["conversion_from_start"]
            leaks = [
                (rep[i]["step"]["value"], rep[i]["conversion_from_prev"])
                for i in range(1, len(rep))
            ]
            worst = min(leaks, key=lambda x: x[1]) if leaks else None
            funnel_line = (
                f"{funnel.name}: {conv:.1%} end-to-end"
                + (f"; biggest leak {worst[0]} ({worst[1]:.0%} continue)" if worst else "")
            )

    project = db.query(Project).filter(Project.id == project_id).first()
    name = project.name if project else "your project"
    week_label = f"{week_start.date().isoformat()} → {now.date().isoformat()}"

    lines = [
        f"Weekly digest — {name} ({week_label})",
        "",
        "The week in numbers (vs prior week):",
        f"• Visitors: {cur['visitors']:,} ({_wow(cur['visitors'], prev['visitors'])} WoW)",
        f"• Pageviews: {cur['pageviews']:,} ({_wow(cur['pageviews'], prev['pageviews'])} WoW)",
        f"• Revenue: {_money(cur['revenue'])} ({_wow(cur['revenue'], prev['revenue'])} WoW)",
        "",
    ]
    if anomalies:
        lines.append(f"Anomalies ({len(anomalies)}):")
        for a in anomalies[:5]:
            date = a["date"] + (f" → {a['date_end']}" if a.get("date_end") else "")
            val = _money(a["value"]) if a["metric"] == "revenue" else f"{a['value']:,.0f}"
            exp = _money(a["expected"]) if a["metric"] == "revenue" else f"{a['expected']:,.0f}"
            lines.append(f"• {a['metric']} {a['direction']} {date}: {val} vs ~{exp} (z={a['z_score']})")
        lines.append("")
    else:
        lines += ["Anomalies: none this week.", ""]
    if top_camps:
        lines.append("Top content by attributed revenue:")
        lines += [f"• {c}: {_money(r)}" for c, r in top_camps]
        lines.append("")
    if funnel_line:
        lines += [f"Funnel: {funnel_line}", ""]
    lines.append("Ask your AI agent \"why\" about any of these for a grounded explanation.")

    body = "\n".join(lines)
    subject = f"AgentLens weekly — {name}: {_money(cur['revenue'])} revenue ({_wow(cur['revenue'], prev['revenue'])} WoW)"
    return {
        "subject": subject,
        "body": body,
        "week_start": week_start.date().isoformat(),
        "week_end": now.date().isoformat(),
        "stats": {
            "visitors": cur["visitors"],
            "pageviews": cur["pageviews"],
            "revenue": cur["revenue"],
            "anomalies": len(anomalies),
        },
    }


def last_slot(now: datetime, weekday: int, hour_utc: int) -> datetime:
    """Most recent datetime <= now matching the scheduled weekday/hour (UTC)."""
    now = _aware(now) or datetime.now(timezone.utc)
    days_back = (now.weekday() - weekday) % 7
    slot = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0) - timedelta(days=days_back)
    if slot > now:
        slot -= timedelta(days=7)
    return slot


def is_due(setting: DigestSetting, now: datetime | None = None) -> bool:
    now = _aware(now) or datetime.now(timezone.utc)
    slot = last_slot(now, setting.weekday, setting.hour_utc)
    last = _aware(setting.last_sent_at)
    return last is None or last < slot


def send_digest(db: Session, project_id: str) -> dict:
    """Compile and deliver the digest to all enabled channels. Returns summary."""
    channels = (
        db.query(AlertChannel)
        .filter(AlertChannel.project_id == project_id, AlertChannel.enabled.is_(True))
        .all()
    )
    if not channels:
        return {"project_id": project_id, "sent": 0, "reason": "no enabled channels"}
    compiled = compile_weekly(db, project_id)
    sent, failed = 0, 0
    for c in channels:
        ok, detail = notify.deliver(c.kind, c.target, compiled["subject"], compiled["body"])
        if ok:
            sent += 1
        else:
            failed += 1
    # Only advance the ledger when at least one channel received it — total
    # failure means the next scheduler tick retries instead of skipping a week.
    if sent:
        setting = db.query(DigestSetting).filter(DigestSetting.project_id == project_id).first()
        if setting:
            setting.last_sent_at = datetime.now(timezone.utc)
            db.commit()
    return {"project_id": project_id, "sent": sent, "failed": failed}


def check_digests() -> list[dict]:
    """Scheduler entrypoint: send due digests."""
    db = SessionLocal()
    try:
        settings = db.query(DigestSetting).filter(DigestSetting.enabled.is_(True)).all()
        out = []
        for s in settings:
            if is_due(s, datetime.now(timezone.utc)):
                out.append(send_digest(db, s.project_id))
        return out
    finally:
        db.close()
