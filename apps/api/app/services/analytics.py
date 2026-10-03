"""Analytics query engine.

v1 design: portable Python-side aggregation over indexed event rows (SQLite and
Postgres compatible). At production scale this moves to materialized rollups —
see docs/architecture.md.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Event

DIMENSIONS = {
    "path": "path",
    "referrer": "referrer",
    "utm_source": "utm_source",
    "utm_medium": "utm_medium",
    "utm_campaign": "utm_campaign",
    "device": "device",
    "browser": "browser",
    "os": "os",
    "country": "country",
    "event": "name",
}

METRICS = ("visitors", "pageviews", "sessions", "events", "revenue")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize everything to naive UTC for bucketing."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def parse_range(date_from: str | None, date_to: str | None) -> tuple[datetime, datetime]:
    end = utcnow()
    if date_to:
        end = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(days=30)
    if date_from:
        start = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    return start, end


def _base_query(db: Session, project_id: str, start: datetime, end: datetime):
    return (
        db.query(Event)
        .filter(
            Event.project_id == project_id,
            Event.created_at >= start,
            Event.created_at <= end,
        )
    )


def _is_pageview(e: Event) -> bool:
    return e.name == "pageview"


def referrer_domain(ref: str) -> str:
    if not ref:
        return "(direct)"
    try:
        host = urlparse(ref).hostname or ""
        return host.removeprefix("www.") or "(direct)"
    except Exception:
        return "(direct)"


def overview(db: Session, project_id: str, start: datetime, end: datetime) -> dict:
    events = _base_query(db, project_id, start, end).all()
    visitors = {e.visitor_id for e in events if e.visitor_id}
    pageviews = [e for e in events if _is_pageview(e)]
    sessions: dict[str, list[Event]] = defaultdict(list)
    for e in pageviews:
        if e.session_id:
            sessions[e.session_id].append(e)
    n_sessions = len(sessions)
    bounced = sum(1 for s in sessions.values() if len(s) == 1)
    durations = []
    for s in sessions.values():
        times = sorted(e.created_at for e in s)
        durations.append((times[-1] - times[0]).total_seconds())
    non_pv = [e for e in events if not _is_pageview(e) and e.name != "revenue"]
    revenue = sum(e.revenue_amount or 0 for e in events)
    currency = next((e.revenue_currency for e in events if e.revenue_currency), "USD")
    return {
        "visitors": len(visitors),
        "pageviews": len(pageviews),
        "sessions": n_sessions,
        "bounce_rate": round(bounced / n_sessions, 4) if n_sessions else 0.0,
        "avg_session_seconds": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "events": len(non_pv),
        "revenue": round(revenue, 2),
        "revenue_currency": currency,
    }


def timeseries(
    db: Session, project_id: str, metric: str, start: datetime, end: datetime, interval: str = "day"
) -> list[dict]:
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; choose from {METRICS}")
    start, end = _naive_utc(start), _naive_utc(end)
    events = _base_query(db, project_id, start, end).all()
    step = timedelta(hours=1) if interval == "hour" else timedelta(days=1)
    buckets: dict[str, dict] = {}

    def bucket_key(dt: datetime) -> str:
        b = dt.replace(minute=0, second=0, microsecond=0) if interval == "hour" else dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return b.isoformat()

    cur = start.replace(minute=0, second=0, microsecond=0)
    if interval == "day":
        cur = cur.replace(hour=0)
    while cur <= end:
        buckets[bucket_key(cur)] = {"visitors": set(), "sessions": set(), "pageviews": 0, "events": 0, "revenue": 0.0}
        cur += step

    for e in events:
        key = bucket_key(_naive_utc(e.created_at))
        b = buckets.get(key)
        if b is None:
            continue
        if e.visitor_id:
            b["visitors"].add(e.visitor_id)
        if e.session_id:
            b["sessions"].add(e.session_id)
        if _is_pageview(e):
            b["pageviews"] += 1
        else:
            b["events"] += 1
        b["revenue"] += e.revenue_amount or 0

    out = []
    for key in sorted(buckets):
        b = buckets[key]
        if metric == "visitors":
            val = len(b["visitors"])
        elif metric == "sessions":
            val = len(b["sessions"])
        else:
            val = b[metric]  # pageviews | events | revenue are plain numbers
        out.append({"t": key, "value": round(val, 2) if isinstance(val, float) else val})
    return out


def breakdown(
    db: Session, project_id: str, dimension: str, start: datetime, end: datetime, limit: int = 20
) -> list[dict]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}; choose from {list(DIMENSIONS)}")
    col = DIMENSIONS[dimension]
    events = _base_query(db, project_id, start, end).all()
    if dimension == "event":
        events = [e for e in events if not _is_pageview(e)]
    groups: dict[str, dict] = defaultdict(lambda: {"visitors": set(), "pageviews": 0, "revenue": 0.0})
    for e in events:
        raw = getattr(e, col) or ""
        value = referrer_domain(raw) if dimension == "referrer" else (raw or "(not set)")
        if dimension == "path" and not value:
            value = "/"
        g = groups[value]
        if e.visitor_id:
            g["visitors"].add(e.visitor_id)
        if _is_pageview(e):
            g["pageviews"] += 1
        g["revenue"] += e.revenue_amount or 0
    rows = [
        {
            "value": v,
            "visitors": len(g["visitors"]),
            "pageviews": g["pageviews"],
            "revenue": round(g["revenue"], 2),
        }
        for v, g in groups.items()
    ]
    rows.sort(key=lambda r: (r["visitors"], r["pageviews"]), reverse=True)
    return rows[:limit]


def realtime(db: Session, project_id: str, minutes: int = 30) -> dict:
    end = utcnow()
    start = end - timedelta(minutes=minutes)
    events = _base_query(db, project_id, start, end).all()
    visitors = {e.visitor_id for e in events if e.visitor_id}
    pages: dict[str, int] = defaultdict(int)
    for e in events:
        if _is_pageview(e):
            pages[e.path or "/"] += 1
    top_pages = sorted(pages.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "visitors": len(visitors),
        "pageviews": sum(1 for e in events if _is_pageview(e)),
        "events": sum(1 for e in events if not _is_pageview(e)),
        "top_pages": [{"path": p, "views": c} for p, c in top_pages],
        "window_minutes": minutes,
    }


def revenue_report(db: Session, project_id: str, start: datetime, end: datetime) -> dict:
    events = _base_query(db, project_id, start, end).all()
    rev_events = [e for e in events if (e.revenue_amount or 0) > 0]
    total = sum(e.revenue_amount for e in rev_events)
    currency = next((e.revenue_currency for e in rev_events if e.revenue_currency), "USD")
    visitors = {e.visitor_id for e in events if e.visitor_id}
    by_source: dict[str, float] = defaultdict(float)
    for e in rev_events:
        src = e.utm_source or referrer_domain(e.referrer)
        by_source[src] += e.revenue_amount
    series = timeseries(db, project_id, "revenue", start, end)
    return {
        "total": round(total, 2),
        "currency": currency,
        "transactions": len(rev_events),
        "revenue_per_visitor": round(total / len(visitors), 2) if visitors else 0.0,
        "by_source": [
            {"source": s, "revenue": round(v, 2)} for s, v in sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)[:15]
        ],
        "timeseries": series,
    }


def funnel_report(db: Session, project_id: str, steps: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Ordered funnel: visitors must complete steps in order (by first occurrence time)."""
    events = _base_query(db, project_id, start, end).order_by(Event.created_at).all()

    def matches(e: Event, step: dict) -> bool:
        kind, value = step.get("kind"), step.get("value", "")
        if kind == "page":
            return _is_pageview(e) and (e.path or "/") == value
        if kind == "event":
            return e.name == value
        return False

    # first-occurrence time per visitor per step
    first: list[dict[str, datetime]] = []
    for step in steps:
        occ: dict[str, datetime] = {}
        for e in events:
            if e.visitor_id and matches(e, step) and e.visitor_id not in occ:
                occ[e.visitor_id] = e.created_at
        first.append(occ)

    converted = set(first[0].keys()) if first else set()
    counts = [len(converted)]
    for i in range(1, len(steps)):
        prev_times = first[i - 1]
        cur_times = first[i]
        converted = {v for v in converted if v in cur_times and cur_times[v] >= prev_times[v]}
        counts.append(len(converted))

    out = []
    for i, step in enumerate(steps):
        conv_start = counts[i] / counts[0] if counts[0] else 0.0
        conv_prev = counts[i] / counts[i - 1] if i and counts[i - 1] else (1.0 if i == 0 else 0.0)
        out.append(
            {
                "step": step,
                "visitors": counts[i],
                "conversion_from_start": round(conv_start, 4),
                "conversion_from_prev": round(conv_prev, 4),
            }
        )
    return out


def mcp_usage(db: Session, project_id: str, start: datetime, end: datetime) -> dict:
    """Direction-2 analytics: how AI agents are using this project's MCP server."""
    calls = (
        _base_query(db, project_id, start, end)
        .filter(Event.name == "mcp_tool_call")
        .all()
    )
    by_tool: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "total_ms": 0.0})
    for e in calls:
        tool = (e.props or {}).get("tool", "unknown")
        b = by_tool[tool]
        b["calls"] += 1
        b["total_ms"] += float((e.props or {}).get("duration_ms", 0))
        if not (e.props or {}).get("success", True):
            b["errors"] += 1
    questions = [
        (e.props or {}).get("question", "")
        for e in _base_query(db, project_id, start, end).filter(Event.name == "ask").all()
        if (e.props or {}).get("question")
    ]
    return {
        "total_tool_calls": len(calls),
        "by_tool": [
            {
                "tool": t,
                "calls": b["calls"],
                "error_rate": round(b["errors"] / b["calls"], 4) if b["calls"] else 0,
                "avg_ms": round(b["total_ms"] / b["calls"], 1) if b["calls"] else 0,
            }
            for t, b in sorted(by_tool.items(), key=lambda kv: kv[1]["calls"], reverse=True)
        ],
        "questions_asked": len(questions),
        "recent_questions": questions[-10:],
    }


def dimension_values(
    db: Session, project_id: str, dimension: str, start: datetime, end: datetime, limit: int = 50
) -> list[str]:
    rows = breakdown(db, project_id, dimension, start, end, limit=limit)
    return [r["value"] for r in rows]
