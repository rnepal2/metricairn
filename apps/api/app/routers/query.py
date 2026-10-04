"""Read-only analytics queries. All scoped to the read key's project."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_read_key
from app.models import ApiKey
from app.services import analytics, anomaly
from app.services.analytics import DIMENSIONS, METRICS, parse_range

router = APIRouter(prefix="/api/v1/query", tags=["query"])


@router.get("/overview")
def overview(
    date_from: str | None = None,
    date_to: str | None = None,
    currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    start, end = parse_range(date_from, date_to)
    return analytics.overview(db, key.project_id, start, end, currency)


@router.get("/timeseries")
def timeseries(
    metric: str = Query(default="visitors", description=f"one of {METRICS}"),
    interval: str = Query(default="day", pattern="^(day|hour)$"),
    date_from: str | None = None,
    date_to: str | None = None,
    currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    start, end = parse_range(date_from, date_to)
    return analytics.timeseries(db, key.project_id, metric, start, end, interval, currency)


@router.get("/breakdown")
def breakdown(
    dimension: str = Query(description=f"one of {list(DIMENSIONS)}"),
    order_by: str = Query(default="visitors", pattern="^(visitors|pageviews|events|revenue)$"),
    limit: int = Query(default=20, ge=1, le=100),
    date_from: str | None = None,
    date_to: str | None = None,
    currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    start, end = parse_range(date_from, date_to)
    return analytics.breakdown(db, key.project_id, dimension, start, end, limit, currency, order_by)


@router.get("/dimensions")
def dimensions(
    dimension: str = Query(description=f"one of {list(DIMENSIONS)}"),
    date_from: str | None = None,
    date_to: str | None = None,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    """Discover which values a dimension actually has — built for agents."""
    start, end = parse_range(date_from, date_to)
    return {
        "dimension": dimension,
        "values": analytics.dimension_values(db, key.project_id, dimension, start, end),
    }


@router.get("/realtime")
def realtime(
    minutes: int = Query(default=30, ge=1, le=1440),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    return analytics.realtime(db, key.project_id, minutes)


@router.get("/revenue")
def revenue(
    date_from: str | None = None,
    date_to: str | None = None,
    currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    start, end = parse_range(date_from, date_to)
    return analytics.revenue_report(db, key.project_id, start, end, currency)


@router.get("/anomalies")
def anomalies(
    date_from: str | None = None,
    date_to: str | None = None,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    start, end = parse_range(date_from, date_to)
    return anomaly.detect(db, key.project_id, start, end)


@router.get("/mcp-usage")
def mcp_usage(
    date_from: str | None = None,
    date_to: str | None = None,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    """How AI agents are using this project's MCP server (direction-2 analytics)."""
    start, end = parse_range(date_from, date_to)
    return analytics.mcp_usage(db, key.project_id, start, end)


@router.get("/metrics")
def list_metrics():
    """Metric/dimension catalog — the agent's entry point for discovery."""
    return {
        "metric_version": "1",
        "query_plan_endpoint": "/api/v1/query/run",
        "metrics": [
            {"name": "visitors", "description": "Unique visitors (distinct visitor_id)"},
            {"name": "pageviews", "description": "Pageview events"},
            {"name": "sessions", "description": "Distinct nonempty session IDs on pageviews"},
            {
                "name": "events",
                "description": "Custom event occurrences (excludes pageviews, revenue and internal telemetry)",
            },
            {
                "name": "event_count",
                "description": "Occurrences of the specified event; use /query/run with event_name",
            },
            {"name": "revenue", "description": "Sum of revenue_amount on revenue events"},
        ],
        "dimensions": [
            {"name": d, "description": desc}
            for d, desc in [
                ("path", "Page path, e.g. /pricing"),
                ("referrer", "Referring domain, (direct) if none"),
                ("utm_source", "UTM source"),
                ("utm_medium", "UTM medium"),
                ("utm_campaign", "UTM campaign"),
                ("device", "desktop | mobile | tablet"),
                ("browser", "Browser family"),
                ("os", "OS family"),
                ("country", "Country, if provided by the tracker"),
                ("event", "Custom event name"),
            ]
        ],
    }


@router.get("/compare")
def compare(
    date_from: str | None = None,
    date_to: str | None = None,
    currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    start, end = parse_range(date_from, date_to)
    return analytics.compare(db, key.project_id, start, end, currency)
