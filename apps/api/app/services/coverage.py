"""Integration health: is the customer's instrumentation actually flowing?

The silent failure mode of event analytics: the founder installs the browser
tracker, never wires server-side revenue events, and the agent can't answer
revenue questions. These checks make that visible instead of silent.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.models import Event, Funnel, Note

# Event names written by AgentLens itself — not customer instrumentation.
_SYSTEM_EVENTS = ["ask"]


def _count(db, project_id, name=None, since=None, before=None, exclude_system=False):
    q = db.query(func.count(Event.id)).filter(Event.project_id == project_id)
    if name is not None:
        q = q.filter(Event.name == name)
    if exclude_system:
        q = q.filter(Event.name.notin_(_SYSTEM_EVENTS))
    if since is not None:
        q = q.filter(Event.created_at >= since)
    if before is not None:
        q = q.filter(Event.created_at <= before)
    return q.scalar() or 0


def health(db, project_id) -> dict:
    """Checklist of integration health. The 7-day window answers 'is it
    working *now*'; statuses are ok | warning | missing."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(days=1)

    pageviews = _count(db, project_id, "pageview", week_ago)
    revenue = _count(db, project_id, "revenue", week_ago)
    custom = _count(db, project_id, since=week_ago, exclude_system=True) - pageviews - revenue
    funnels = db.query(func.count(Funnel.id)).filter(Funnel.project_id == project_id).scalar() or 0
    notes = db.query(func.count(Note.id)).filter(Note.project_id == project_id).scalar() or 0
    last_event = (
        db.query(func.max(Event.created_at)).filter(Event.project_id == project_id).scalar()
    )
    if last_event is not None and last_event.tzinfo is None:
        # SQLite returns naive datetimes; treat stored times as UTC.
        last_event = last_event.replace(tzinfo=timezone.utc)

    checks = [
        {
            "key": "tracker",
            "label": "Browser tracker sending pageviews",
            "status": "ok" if pageviews > 0 else "missing",
            "detail": f"{pageviews:,} pageviews in the last 7 days" if pageviews else "No pageviews in 7 days — is the snippet installed?",
        },
        {
            "key": "revenue",
            "label": "Server-side revenue events",
            "status": "ok" if revenue > 0 else "missing",
            "detail": f"{revenue:,} revenue events in the last 7 days" if revenue else (
                "No revenue events — every revenue answer depends on these "
                "(Settings → Installation → Server events, or the Stripe webhook)."
            ),
        },
        {
            "key": "custom_events",
            "label": "Custom events (signup, etc.)",
            "status": "ok" if custom > 0 else "warning",
            "detail": f"{custom:,} custom events in the last 7 days" if custom else "No custom events yet — funnels and conversion answers need them.",
        },
        {
            "key": "funnels",
            "label": "Funnels defined",
            "status": "ok" if funnels > 0 else "warning",
            "detail": f"{funnels} funnel(s) defined" if funnels else "No funnels yet — define one under Funnels.",
        },
        {
            "key": "live",
            "label": "Receiving live data",
            "status": "ok" if last_event and last_event >= day_ago else ("warning" if last_event else "missing"),
            "detail": f"Last event {last_event.isoformat()}" if last_event else "No events ever received.",
        },
        {
            "key": "notes",
            "label": "Timeline notes",
            "status": "ok" if notes > 0 else "warning",
            "detail": f"{notes} note(s) on the timeline" if notes else "No notes — they make 'why' answers dramatically better.",
        },
    ]
    missing = [c["key"] for c in checks if c["status"] == "missing"]
    return {"project_id": project_id, "checks": checks, "missing": missing}


def coverage_notes(db, project_id, action: str, start, end) -> list[str]:
    """Per-question honesty notes: what the answer *couldn't* see.

    Called by the ask endpoint so the agent (and the dashboard) never present
    a confident-sounding answer built on absent data.
    """
    notes: list[str] = []
    total = _count(db, project_id, since=start, before=end)
    if total == 0:
        return [
            "No events at all in this period — check the tracker snippet is installed "
            "(Settings → Installation). This answer is based on an empty dataset."
        ]

    revenue_in_range = (
        db.query(func.count(Event.id))
        .filter(
            Event.project_id == project_id,
            Event.name == "revenue",
            Event.created_at >= start,
            Event.created_at <= end,
        )
        .scalar()
        or 0
    )
    if action in ("revenue", "revenue_by_source") and revenue_in_range == 0:
        notes.append(
            "No revenue events in this period — revenue answers need the server-side "
            "revenue snippet or Stripe webhook (see docs/trust-and-data.md). "
            "Totals above are $0 because nothing was sent, not because revenue was zero."
        )
    if action == "anomalies" and revenue_in_range == 0:
        notes.append(
            "Anomaly scan covered pageviews only — no revenue events in range, "
            "so revenue dips/spikes could not be checked."
        )
    if action == "explain":
        notes_in_range = (
            db.query(func.count(Note.id))
            .filter(
                Note.project_id == project_id,
                Note.at >= start,
                Note.at <= end,
            )
            .scalar()
            or 0
        )
        if notes_in_range == 0:
            notes.append(
                "No timeline notes in this period — 'why' answers are much better with "
                "notes (log deploys via MCP add_note or Settings)."
            )
    return notes

def based_on(db, project_id, start, end) -> dict:
    """Structured provenance for an ask answer: how much data backed it.

    Every answer carries this footer so a founder (or their agent) can tell
    'answered from 12,000 events' apart from 'answered from 3 events'.
    System events (ask logs) are excluded — they aren't customer data.
    """
    base = (
        db.query(Event)
        .filter(
            Event.project_id == project_id,
            Event.created_at >= start,
            Event.created_at <= end,
            Event.name.notin_(_SYSTEM_EVENTS),
        )
    )
    names = sorted(r[0] for r in base.with_entities(Event.name).distinct().limit(25).all())
    return {
        "events": base.count(),
        "event_names": names,
        "date_range": {"from": start.date().isoformat(), "to": end.date().isoformat()},
    }
