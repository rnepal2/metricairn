"""Analytics query engine.

Core metrics aggregate in the database (SQLite and Postgres compatible).
Funnels and referrer parsing stream rows. At larger scale add rollups —
see docs/architecture.md.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import case, distinct, func
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

SYSTEM_EVENTS = ("ask", "mcp_tool_call")

METRICS = ("visitors", "pageviews", "sessions", "events", "revenue")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize everything to naive UTC for bucketing."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def parse_range(date_from: str | None, date_to: str | None) -> tuple[datetime, datetime]:
    """UTC [start, end). A date-only end includes that calendar day."""

    def parse(value: str) -> datetime:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise ValueError("Dates must be ISO 8601 dates or timestamps") from None
        return (
            result.replace(tzinfo=timezone.utc)
            if result.tzinfo is None
            else result.astimezone(timezone.utc)
        )

    end = parse(date_to) if date_to else utcnow()
    if date_to and len(date_to) == 10:
        end += timedelta(days=1)
    start = parse(date_from) if date_from else end - timedelta(days=30)
    if start >= end:
        raise ValueError("date_from must be before date_to")
    if end - start > timedelta(days=366):
        raise ValueError("Query windows are limited to 366 days")
    return start, end


def _base_query(db: Session, project_id: str, start: datetime, end: datetime, include_system=False):
    query = db.query(Event).filter(
        Event.project_id == project_id, Event.created_at >= start, Event.created_at < end
    )
    return query if include_system else query.filter(Event.name.notin_(SYSTEM_EVENTS))


def revenue_currencies(db, project_id, start, end) -> list[str]:
    rows = (
        _base_query(db, project_id, start, end)
        .filter(Event.name == "revenue")
        .with_entities(Event.revenue_currency)
        .distinct()
        .all()
    )
    return sorted({r[0] or "USD" for r in rows})


def _currency(db, project_id, start, end, requested=None) -> str:
    currencies = revenue_currencies(db, project_id, start, end)
    if requested:
        if len(requested) != 3 or not requested.isalpha():
            raise ValueError("currency must be a three-letter code")
        return requested.upper()
    return "USD" if "USD" in currencies else (currencies[0] if currencies else "USD")


def _amount(event, currency):
    return (
        (event.revenue_amount or 0)
        if event.name == "revenue" and (event.revenue_currency or "USD") == currency
        else 0
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


def _money_expr(currency):
    return case(
        (
            (Event.name == "revenue")
            & (func.coalesce(func.nullif(Event.revenue_currency, ""), "USD") == currency),
            func.coalesce(Event.revenue_amount, 0),
        ),
        else_=0,
    )


def _aggregates(currency):
    return [
        func.count(distinct(func.nullif(Event.visitor_id, ""))).label("visitors"),
        func.sum(case((Event.name == "pageview", 1), else_=0)).label("pageviews"),
        func.count(
            distinct(
                case((Event.name == "pageview", func.nullif(Event.session_id, "")), else_=None)
            )
        ).label("sessions"),
        func.sum(case((Event.name.notin_(("pageview", "revenue")), 1), else_=0)).label("events"),
        func.sum(_money_expr(currency)).label("revenue"),
    ]


def overview(
    db: Session, project_id: str, start: datetime, end: datetime, currency: str | None = None
) -> dict:
    currency = _currency(db, project_id, start, end, currency)
    base = _base_query(db, project_id, start, end)
    row = base.with_entities(*_aggregates(currency)).one()
    out = {
        key: int(getattr(row, key) or 0) for key in ("visitors", "pageviews", "sessions", "events")
    }
    sessions = (
        base.filter(Event.name == "pageview", Event.session_id != "")
        .with_entities(
            func.count(Event.id).label("views"),
            func.min(Event.created_at).label("first"),
            func.max(Event.created_at).label("last"),
        )
        .group_by(Event.session_id)
        .subquery()
    )
    if db.get_bind().dialect.name == "postgresql":
        duration = func.extract("epoch", sessions.c.last - sessions.c.first)
    else:
        duration = (func.julianday(sessions.c.last) - func.julianday(sessions.c.first)) * 86400
    summary = (
        db.query(
            func.count(), func.sum(case((sessions.c.views == 1, 1), else_=0)), func.avg(duration)
        )
        .select_from(sessions)
        .one()
    )
    out.update(
        {
            "bounce_rate": round((summary[1] or 0) / summary[0], 4) if summary[0] else 0.0,
            "avg_session_seconds": round(float(summary[2] or 0), 1),
            "revenue": round(float(row.revenue or 0), 2),
            "revenue_currency": currency,
            "revenue_currencies": revenue_currencies(db, project_id, start, end),
        }
    )
    return out


def timeseries(
    db: Session,
    project_id: str,
    metric: str,
    start: datetime,
    end: datetime,
    interval: str = "day",
    currency: str | None = None,
) -> list[dict]:
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; choose from {METRICS}")
    if interval not in ("day", "hour"):
        raise ValueError("interval must be day or hour")
    currency = _currency(db, project_id, start, end, currency)

    def floor(dt):
        dt = _naive_utc(dt).replace(minute=0, second=0, microsecond=0)
        return dt if interval == "hour" else dt.replace(hour=0)

    if db.get_bind().dialect.name == "postgresql":
        bucket = func.date_trunc(interval, Event.created_at)
    else:
        pattern = "%Y-%m-%dT%H:00:00" if interval == "hour" else "%Y-%m-%dT00:00:00"
        bucket = func.strftime(pattern, Event.created_at)
    expression = next(value for value in _aggregates(currency) if value.name == metric)
    rows = (
        _base_query(db, project_id, start, end)
        .with_entities(bucket.label("bucket"), expression)
        .group_by(bucket)
        .all()
    )
    observed = {
        floor(row[0]).isoformat() if isinstance(row[0], datetime) else row[0]: row[1] or 0
        for row in rows
    }
    current, stop = floor(start), _naive_utc(end)
    step = timedelta(hours=1) if interval == "hour" else timedelta(days=1)
    out = []
    while current < stop:
        value = observed.get(current.isoformat(), 0)
        out.append(
            {
                "t": current.isoformat(),
                "value": round(float(value), 2) if metric == "revenue" else int(value),
            }
        )
        current += step
    return out


def breakdown(
    db: Session,
    project_id: str,
    dimension: str,
    start: datetime,
    end: datetime,
    limit: int = 20,
    currency: str | None = None,
    order_by: str = "visitors",
) -> list[dict]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}; choose from {list(DIMENSIONS)}")
    if order_by not in ("visitors", "pageviews", "events", "revenue"):
        raise ValueError("Unsupported breakdown ordering")
    currency = _currency(db, project_id, start, end, currency)
    base = _base_query(db, project_id, start, end)
    if dimension == "event":
        base = base.filter(Event.name != "pageview")
    if dimension == "path":
        base = base.filter(Event.path != "")  # Missing server context is not a visit to /
    if dimension == "referrer":
        # Host parsing is portable Python; stream rows instead of retaining ORM events.
        groups = defaultdict(
            lambda: {"visitors": set(), "pageviews": 0, "events": 0, "revenue": 0.0}
        )
        for event in base.yield_per(2000):
            group = groups[referrer_domain(event.referrer)]
            if event.visitor_id:
                group["visitors"].add(event.visitor_id)
            group["pageviews"] += int(_is_pageview(event))
            group["events"] += 1
            group["revenue"] += _amount(event, currency)
        rows = [
            {
                "value": name,
                **{key: value for key, value in group.items() if key != "visitors"},
                "visitors": len(group["visitors"]),
            }
            for name, group in groups.items()
        ]
        rows.sort(key=lambda row: (row[order_by], row["visitors"], row["value"]), reverse=True)
        for row in rows:
            row["revenue"] = round(row["revenue"], 2)
        return rows[:limit]
    col = getattr(Event, DIMENSIONS[dimension])
    value = func.coalesce(func.nullif(col, ""), "/" if dimension == "path" else "(not set)")
    visitors = func.count(distinct(func.nullif(Event.visitor_id, ""))).label("visitors")
    pageviews = func.sum(case((Event.name == "pageview", 1), else_=0)).label("pageviews")
    count = func.count().label("events")
    revenue = func.sum(_money_expr(currency)).label("revenue")
    sort = {"visitors": visitors, "pageviews": pageviews, "events": count, "revenue": revenue}[
        order_by
    ]
    rows = (
        base.with_entities(value.label("value"), visitors, pageviews, count, revenue)
        .group_by(value)
        .order_by(sort.desc(), visitors.desc(), value.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "value": row.value,
            "visitors": row.visitors,
            "pageviews": int(row.pageviews or 0),
            "events": row.events,
            "revenue": round(float(row.revenue or 0), 2),
        }
        for row in rows
    ]


def realtime(db: Session, project_id: str, minutes: int = 30) -> dict:
    end = utcnow()
    start = end - timedelta(minutes=minutes)
    result = overview(db, project_id, start, end)
    rows = (
        _base_query(db, project_id, start, end)
        .filter(Event.name == "pageview")
        .with_entities(Event.path, func.count().label("views"))
        .group_by(Event.path)
        .order_by(func.count().desc())
        .limit(10)
        .all()
    )
    return {
        "visitors": result["visitors"],
        "pageviews": result["pageviews"],
        "events": result["events"],
        "top_pages": [{"path": row.path or "/", "views": row.views} for row in rows],
        "window_minutes": minutes,
    }


def revenue_report(
    db: Session, project_id: str, start: datetime, end: datetime, currency: str | None = None
) -> dict:
    currency = _currency(db, project_id, start, end, currency)
    base = _base_query(db, project_id, start, end)
    revenue = base.filter(
        Event.name == "revenue",
        func.coalesce(func.nullif(Event.revenue_currency, ""), "USD") == currency,
        Event.revenue_amount > 0,
    )
    total, transactions = revenue.with_entities(func.sum(Event.revenue_amount), func.count()).one()
    total = float(total or 0)
    visitors = (
        base.with_entities(func.count(distinct(func.nullif(Event.visitor_id, "")))).scalar() or 0
    )
    identity = case((Event.visitor_id != "", 1), else_=0)
    rows = (
        revenue.with_entities(
            Event.utm_source,
            Event.referrer,
            identity.label("identified"),
            func.sum(Event.revenue_amount).label("amount"),
        )
        .group_by(Event.utm_source, Event.referrer, identity)
        .all()
    )
    by_source = defaultdict(float)
    tagged = 0
    for row in rows:
        source = row.utm_source or (
            referrer_domain(row.referrer)
            if row.referrer
            else ("(direct)" if row.identified else "(unattributed)")
        )
        by_source[source] += float(row.amount)
        if row.utm_source or row.referrer:
            tagged += float(row.amount)
    return {
        "total": round(total, 2),
        "currency": currency,
        "currencies": revenue_currencies(db, project_id, start, end),
        "transactions": transactions,
        "attribution_model": "event-stamped session landing source; unmatched server payments are unattributed",
        "attributed_revenue_share": round(tagged / total, 4) if total else None,
        "revenue_per_visitor": round(total / visitors, 2) if visitors else 0.0,
        "by_source": [
            {"source": source, "revenue": round(amount, 2)}
            for source, amount in sorted(by_source.items(), key=lambda item: item[1], reverse=True)[
                :15
            ]
        ],
        "timeseries": timeseries(db, project_id, "revenue", start, end, currency=currency),
    }


def _dim_value(e: Event, dimension: str) -> str:
    """Display value of a dimension on one event, with the same rules as breakdown."""
    col = DIMENSIONS[dimension]
    raw = getattr(e, col) or ""
    if dimension == "referrer":
        return referrer_domain(raw) or "(not set)"
    if dimension == "path":
        return raw or "/"
    return raw or "(not set)"


def _funnel_firsts(
    db: Session, project_id: str, steps: list[dict], start: datetime, end: datetime
) -> tuple[list[dict[str, datetime]], dict[str, "Event"]]:
    """First-occurrence time per visitor per step, plus each visitor's step-0
    event (for segment attribution)."""
    events = (
        _base_query(db, project_id, start, end).order_by(Event.created_at, Event.id).yield_per(2000)
    )

    def matches(e: Event, step: dict) -> bool:
        kind, value = step.get("kind"), step.get("value", "")
        if kind == "page":
            return _is_pageview(e) and (e.path or "/") == value
        if kind == "event":
            return e.name == value
        return False

    first: list[dict[str, datetime]] = [{} for _ in steps]
    entry_event: dict[str, Event] = {}
    progress: dict[str, int] = defaultdict(int)
    for e in events:
        visitor = e.visitor_id
        index = progress[visitor]
        if not visitor or index >= len(steps) or not matches(e, steps[index]):
            continue
        first[index][visitor] = e.created_at
        progress[visitor] += 1
        if index == 0:
            entry_event[visitor] = e
    return first, entry_event


def _conversion_steps(first: list[dict[str, datetime]], steps: list[dict]) -> list[dict]:
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


def funnel_report(
    db: Session, project_id: str, steps: list[dict], start: datetime, end: datetime
) -> list[dict]:
    """Ordered funnel: visitors must complete steps in order (by first occurrence time)."""
    first, _ = _funnel_firsts(db, project_id, steps, start, end)
    return _conversion_steps(first, steps)


def funnel_report_by_segment(
    db: Session,
    project_id: str,
    steps: list[dict],
    start: datetime,
    end: datetime,
    segment_by: str,
    max_segments: int = 8,
) -> list[dict]:
    """Same ordered funnel, computed per segment.

    A visitor's segment is the dimension value on their *entry-step* (step 0)
    event — the device, source, etc. they arrived with. Documented choice:
    dimensions can vary across a visitor's events, so we anchor on entry.
    Returns the top segments by entry visitors, each with its own step table.
    """
    if segment_by not in DIMENSIONS:
        raise ValueError(f"unknown dimension {segment_by!r}; choose from {list(DIMENSIONS)}")
    first, entry_event = _funnel_firsts(db, project_id, steps, start, end)

    # segment per visitor from their step-0 event
    by_seg: dict[str, set[str]] = {}
    for v, e in entry_event.items():
        by_seg.setdefault(_dim_value(e, segment_by), set()).add(v)
    top = sorted(by_seg.items(), key=lambda kv: len(kv[1]), reverse=True)[:max_segments]

    out = []
    for value, visitors in top:
        seg_first = [{v: t for v, t in occ.items() if v in visitors} for occ in first]
        seg_steps = _conversion_steps(seg_first, steps)
        out.append(
            {
                "value": value,
                "visitors": len(visitors),
                "overall_conversion": seg_steps[-1]["conversion_from_start"] if seg_steps else 0.0,
                "steps": seg_steps,
            }
        )
    return out


def mcp_usage(db: Session, project_id: str, start: datetime, end: datetime) -> dict:
    """Direction-2 analytics: how AI agents are using this project's MCP server."""
    calls = (
        _base_query(db, project_id, start, end, include_system=True)
        .filter(Event.name == "mcp_tool_call")
        .all()
    )
    by_tool: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "total_ms": 0.0})
    for e in calls:
        tool = (e.props or {}).get("tool", "unknown")
        b = by_tool[tool]
        b["calls"] += 1
        try:
            b["total_ms"] += max(0, float((e.props or {}).get("duration_ms", 0)))
        except (TypeError, ValueError):
            pass
        if not (e.props or {}).get("success", True):
            b["errors"] += 1
    questions = [
        (e.props or {}).get("question", "")
        for e in _base_query(db, project_id, start, end, include_system=True)
        .filter(Event.name == "ask")
        .all()
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


def compare(db, project_id, start, end, currency=None):
    """Equal-length adjacent windows. Unique metrics use period-wide sets."""
    previous_start = start - (end - start)
    currency = _currency(db, project_id, previous_start, end, currency)
    current = overview(db, project_id, start, end, currency)
    previous = overview(db, project_id, previous_start, start, currency)
    rows = []
    for metric in (*METRICS, "bounce_rate"):
        cur, prev = current[metric], previous[metric]
        rows.append(
            {
                "metric": metric,
                "current": cur,
                "previous": prev,
                "change": round(cur - prev, 4),
                "change_pct": round((cur - prev) / prev * 100, 2) if prev else None,
            }
        )
    return {
        "current_window": {"from": start.isoformat(), "to": end.isoformat()},
        "previous_window": {"from": previous_start.isoformat(), "to": start.isoformat()},
        "currency": currency,
        "metrics": rows,
        "notes": [
            "Descriptive comparison; no statistical significance or causal claim.",
            "A rolling window may include a partial day. Revenue is gross recorded payments, not MRR or net revenue.",
        ],
    }
