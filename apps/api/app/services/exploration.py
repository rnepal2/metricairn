"""Versioned, deterministic analytics plans and reproducible investigations.

All filters are bound SQLAlchemy predicates. No SQL or project selector is accepted
from the caller. Event-stamped segment counts are additive; visitor counts are not.
"""

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, distinct, func

from app.models import Event, Goal, Note
from app.services.analytics import (
    DIMENSIONS,
    SYSTEM_EVENTS,
    _base_query,
    _naive_utc,
    parse_range,
    utcnow,
)

VERSION = "1"
FieldName = Literal[
    "path",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "device",
    "browser",
    "os",
    "country",
    "event",
]
Measure = Literal["pageviews", "visitors", "sessions", "events", "event_count"]


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: FieldName
    values: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def bounded_values(self):
        if any(len(value) > 1000 for value in self.values):
            raise ValueError("Filter values are limited to 1000 characters")
        return self


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Measure = "pageviews"
    event_name: str | None = Field(default=None, min_length=1, max_length=200)
    mode: Literal["total", "timeseries", "breakdown"] = "total"
    dimension: FieldName | None = None
    interval: Literal["day", "hour"] = "day"
    filters: list[Filter] = Field(default_factory=list, max_length=10)
    date_from: str | None = None
    date_to: str | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def valid_plan(self):
        if self.metric == "event_count" and not self.event_name:
            raise ValueError("event_count requires event_name")
        if self.event_name in SYSTEM_EVENTS:
            raise ValueError("Internal telemetry is excluded from customer metrics")
        if self.event_name and self.metric != "event_count":
            raise ValueError("event_name is only supported with event_count")
        if self.mode == "breakdown" and not self.dimension:
            raise ValueError("breakdown requires dimension")
        parse_range(self.date_from, self.date_to)
        return self


def filtered_query(db, project_id, plan, start, end):
    base = _base_query(db, project_id, start, end)
    for constraint in plan.filters:
        base = base.filter(getattr(Event, DIMENSIONS[constraint.field]).in_(constraint.values))
    if plan.metric in ("pageviews", "sessions"):
        base = base.filter(Event.name == "pageview")
    elif plan.metric == "events":
        base = base.filter(Event.name.notin_(("pageview", "revenue")))
    elif plan.metric == "event_count":
        base = base.filter(Event.name == plan.event_name)
    return base


def expression(metric):
    if metric == "visitors":
        return func.count(distinct(func.nullif(Event.visitor_id, "")))
    if metric == "sessions":
        return func.count(distinct(func.nullif(Event.session_id, "")))
    return func.count(Event.id)


def run_plan(db, project_id, plan: QueryPlan):
    start, end = parse_range(plan.date_from, plan.date_to)
    base = filtered_query(db, project_id, plan, start, end)
    value = expression(plan.metric)
    total = int(base.with_entities(value).scalar() or 0)
    rows = []
    truncated = False
    if plan.mode == "breakdown":
        column = getattr(Event, DIMENSIONS[plan.dimension])
        grouped = (
            base.with_entities(column, value)
            .group_by(column)
            .order_by(value.desc(), column.asc())
            .limit(plan.limit + 1)
            .all()
        )
        truncated = len(grouped) > plan.limit
        rows = [
            {"value": name or "(not set)", "count": int(count)}
            for name, count in grouped[: plan.limit]
        ]
    elif plan.mode == "timeseries":
        if db.get_bind().dialect.name == "postgresql":
            bucket = func.date_trunc(plan.interval, Event.created_at)
        else:
            bucket = func.strftime(
                "%Y-%m-%dT%H:00:00" if plan.interval == "hour" else "%Y-%m-%dT00:00:00",
                Event.created_at,
            )
        grouped = base.with_entities(bucket, value).group_by(bucket).all()
        observed = {
            (_naive_utc(t).isoformat() if hasattr(t, "tzinfo") else t): int(count)
            for t, count in grouped
        }
        current = _naive_utc(start).replace(minute=0, second=0, microsecond=0)
        if plan.interval == "day":
            current = current.replace(hour=0)
        step = timedelta(days=1) if plan.interval == "day" else timedelta(hours=1)
        while current < _naive_utc(end):
            rows.append({"t": current.isoformat(), "count": observed.get(current.isoformat(), 0)})
            current += step
    resolved = plan.model_dump() | {"date_from": start.isoformat(), "date_to": end.isoformat()}
    return {
        "metric_version": VERSION,
        "plan": resolved,
        "total": total,
        "rows": rows,
        "truncated": truncated,
        "generated_at": utcnow().isoformat(),
        "notes": [
            "UTC [start, end). Filters are ANDed; values within each filter are ORed.",
            "Counts reflect recorded events, not complete real-world activity.",
            *(
                ["Distinct identities may occur in multiple buckets; do not sum bucket counts."]
                if plan.metric in ("visitors", "sessions")
                else []
            ),
        ],
    }


def goal_report(db, project_id, goal: Goal, start, end):
    base = _base_query(db, project_id, start, end)
    # A conversion requires a pageview followed by this goal, within this window.
    entry = (
        base.filter(Event.name == "pageview", Event.visitor_id != "")
        .with_entities(Event.visitor_id.label("visitor"), func.min(Event.created_at).label("first"))
        .group_by(Event.visitor_id)
        .subquery()
    )
    goal_events = base.filter(Event.name == goal.event_name)
    eligible = db.query(func.count()).select_from(entry).scalar() or 0
    converted = (
        goal_events.join(
            entry, (Event.visitor_id == entry.c.visitor) & (Event.created_at >= entry.c.first)
        )
        .with_entities(func.count(distinct(Event.visitor_id)))
        .scalar()
        or 0
    )
    occurrences = goal_events.with_entities(func.count()).scalar() or 0
    unmatched = goal_events.filter(Event.visitor_id == "").with_entities(func.count()).scalar() or 0
    return {
        "id": goal.id,
        "name": goal.name,
        "event_name": goal.event_name,
        "eligible_visitors": eligible,
        "converted_visitors": converted,
        "conversion_rate": converted / eligible if eligible else None,
        "occurrences": occurrences,
        "unidentified_occurrences": unmatched,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "definition": "Distinct visitors with a pageview then this event in this UTC window. Repeat events count once per visitor. This is period conversion, not an acquisition cohort.",
        "metric_version": VERSION,
    }


def retention(db, project_id, start, end, event_name=None):
    """Weekly first-observed visitor cohorts, with right-censored cells."""
    if event_name in SYSTEM_EVENTS:
        raise ValueError("Internal telemetry is excluded")
    # First seen uses all recorded history before end, preventing returning
    # visitors being silently reassigned as new acquisitions each query window.
    history = (
        db.query(Event.visitor_id, func.min(Event.created_at).label("first"))
        .filter(
            Event.project_id == project_id,
            Event.name.notin_(SYSTEM_EVENTS),
            Event.visitor_id != "",
            Event.created_at < end,
        )
        .group_by(Event.visitor_id)
        .having(func.min(Event.created_at) >= start)
        .all()
    )

    def week(date):
        return _naive_utc(date).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=_naive_utc(date).weekday()
        )

    cohorts = defaultdict(set)
    visitors = {}
    for visitor, first in history:
        label = week(first)
        cohorts[label].add(visitor)
        visitors[visitor] = label
    activity = _base_query(db, project_id, start, end).filter(Event.visitor_id != "")
    if event_name:
        activity = activity.filter(Event.name == event_name)
    active = defaultdict(set)
    for visitor, at in activity.with_entities(Event.visitor_id, Event.created_at).yield_per(2000):
        if visitor in visitors:
            offset = (week(at) - visitors[visitor]).days // 7
            if 0 <= offset <= 12:
                active[(visitors[visitor], offset)].add(visitor)
    cutoff = min(_naive_utc(end), _naive_utc(utcnow()))
    rows = []
    for cohort, members in sorted(cohorts.items()):
        cells = []
        for offset in range(13):
            completed = cohort + timedelta(weeks=offset + 1) <= cutoff
            count = len(active[(cohort, offset)]) if completed else None
            cells.append(
                {
                    "week": offset,
                    "visitors": count,
                    "rate": count / len(members) if count is not None else None,
                }
            )
        rows.append({"cohort": cohort.date().isoformat(), "size": len(members), "weeks": cells})
    return {
        "metric_version": VERSION,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "event_name": event_name,
        "cohorts": rows,
        "notes": [
            "Cohorts use first recorded customer event across available project history, not signup date.",
            "Monday UTC weeks. Incomplete weeks are null, not zero. Week 0 includes acquisition activity.",
            "The first cohort may be partial if the query begins midweek. Cleared IDs and missing history affect retention.",
        ],
    }


def investigate(db, project_id, plan: QueryPlan):
    if plan.metric not in ("pageviews", "events", "event_count"):
        raise ValueError(
            "Investigations support additive event counts: pageviews, events, event_count"
        )
    start, end = parse_range(plan.date_from, plan.date_to)
    if end > utcnow() + timedelta(seconds=5):
        raise ValueError("An investigation must end at or before the present")
    duration = end - start
    previous_start = start - duration
    resolved = plan.model_copy(
        update={"mode": "total", "date_from": start.isoformat(), "date_to": end.isoformat()}
    )
    prior = resolved.model_copy(
        update={"date_from": previous_start.isoformat(), "date_to": start.isoformat()}
    )
    current = run_plan(db, project_id, resolved)
    previous = run_plan(db, project_id, prior)
    delta = current["total"] - previous["total"]
    segments = []
    for dimension in ("utm_source", "device", "browser", "path"):
        column = getattr(Event, DIMENSIONS[dimension])
        # One grouped SQL query across both windows, keeping the entire tail in
        # an explicit residual instead of pretending top-N sums explain all change.
        base = filtered_query(db, project_id, plan, previous_start, end)
        counts = base.with_entities(
            column,
            func.sum(case((Event.created_at >= start, 1), else_=0)),
            func.sum(case((Event.created_at < start, 1), else_=0)),
        ).group_by(column)
        rows = [
            {
                "value": name or "(not set)",
                "current": int(now or 0),
                "previous": int(before or 0),
                "change": int(now or 0) - int(before or 0),
            }
            for name, now, before in counts
        ]
        rows.sort(key=lambda row: (-abs(row["change"]), row["value"]))
        top = rows[:10]
        tail = rows[10:]
        segments.append(
            {
                "dimension": dimension,
                "rows": top,
                "other": {
                    "current": sum(row["current"] for row in tail),
                    "previous": sum(row["previous"] for row in tail),
                    "change": sum(row["change"] for row in tail),
                },
                "total_change": delta,
            }
        )
    coverage = []
    for label, left, right in (("current", start, end), ("previous", previous_start, start)):
        base = _base_query(db, project_id, left, right)
        count, identified, last = base.with_entities(
            func.count(),
            func.sum(case((Event.visitor_id != "", 1), else_=0)),
            func.max(Event.created_at),
        ).one()
        coverage.append(
            {
                "period": label,
                "recorded_events": count,
                "identified_share": identified / count if count else None,
                "last_event_at": last.isoformat() if last else None,
            }
        )
    annotations = (
        db.query(Note)
        .filter(Note.project_id == project_id, Note.at >= previous_start, Note.at < end)
        .order_by(Note.at)
        .limit(101)
        .all()
    )
    caveats = [
        "Segment changes describe where recorded counts changed. They do not establish cause or statistical significance.",
        "Each dimension is a separate partition. Do not add changes across dimensions.",
        "Equal duration does not control for weekday mix, seasonality, outages, or instrumentation changes.",
    ]
    if not previous["total"]:
        caveats.append("The previous baseline is zero; percent change is undefined.")
    if duration < timedelta(days=7):
        caveats.append(
            "Short windows are particularly sensitive to weekday and time-of-day differences."
        )
    if any(not item["recorded_events"] for item in coverage):
        caveats.append(
            "One window has no recorded customer events. Verify collection before interpreting the change."
        )
    report = {
        "metric_version": VERSION,
        "plan": current["plan"],
        "current": current["total"],
        "previous": previous["total"],
        "change": delta,
        "change_pct": delta / previous["total"] * 100 if previous["total"] else None,
        "current_window": {"from": start.isoformat(), "to": end.isoformat()},
        "previous_window": {"from": previous_start.isoformat(), "to": start.isoformat()},
        "segments": segments,
        "coverage": coverage,
        "notes": [{"text": item.text, "at": item.at.isoformat()} for item in annotations[:100]],
        "notes_truncated": len(annotations) > 100,
        "caveats": caveats,
        "next_checks": [
            "Check tracking deployment and missing event/source fields.",
            "Inspect the largest changed segments and compare equivalent weekdays.",
            "Correlate timeline notes with the change; validate a hypothesis before taking action.",
        ],
    }
    # This identifies the exported payload. It is not a raw-data hash or signature.
    report["evidence_id"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report["generated_at"] = utcnow().isoformat()
    return report
