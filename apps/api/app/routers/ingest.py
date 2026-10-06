"""Event ingestion. Write-key scoped to a single project."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import __version__
from app.core.database import get_db
from app.core.security import require_write_key
from app.models import ApiKey, Event
from app.schemas import IngestBatch, IngestEvent, IngestResult

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


@router.get("/ping")
def ping():
    """No-auth reachability check. Proxy your domain's /al/* to /api/v1/*, then
    `curl https://your-domain/al/ingest/ping` — a 200 here proves the proxy
    path works before you touch the snippet."""
    return {"ok": True, "service": "metricairn-ingest", "version": __version__}


BOT_HINTS = ("bot", "crawler", "spider", "headless", "lighthouse", "pingdom")


@router.post("", response_model=IngestResult)
def ingest(
    body: IngestBatch,
    request: Request,
    key: ApiKey = Depends(require_write_key),
    db: Session = Depends(get_db),
):
    ua = (request.headers.get("user-agent") or "").lower()
    if any(h in ua for h in BOT_HINTS):
        return IngestResult(accepted=0, rejected=len(body.events))

    accepted = 0
    for e in body.events:
        if not e.name:
            continue
        utm = _utm_from_url(e.url)
        record = Event(
            event_id=e.event_id,
            project_id=key.project_id,
            session_id=e.session_id[:64],
            visitor_id=e.visitor_id[:64],
            user_id=(e.user_id[:128] if e.user_id else None),
            group_id=(e.group_id[:128] if e.group_id else None),
            name=e.name[:200],
            path=_path_of(e.url),
            url=e.url[:2000],
            referrer=e.referrer[:2000],
            utm_source=utm.get("utm_source", "")[:300],
            utm_medium=utm.get("utm_medium", "")[:300],
            utm_campaign=utm.get("utm_campaign", "")[:300],
            device=e.device[:30],
            browser=e.browser[:60],
            os=e.os[:60],
            country=e.country[:100],
            props=dict(e.props or {}),
            revenue_amount=max(0.0, e.revenue_amount),
            revenue_currency=e.revenue_currency[:10],
            created_at=e.at,
        )
        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
            accepted += 1
        except IntegrityError:
            if not e.event_id:
                raise
            if (
                not db.query(Event.id)
                .filter(Event.project_id == key.project_id, Event.event_id == e.event_id)
                .first()
            ):
                raise
            # A retry is acknowledged without recording it twice.

    db.commit()
    return IngestResult(accepted=accepted, rejected=len(body.events) - accepted)


def _path_of(url: str) -> str:
    """Extract just the path (/pricing) from a full URL."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        return (urlparse(url).path or "/")[:1000]
    except Exception:
        return "/"


def _utm_from_url(url: str) -> dict:
    try:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(url).query)
        return {k: (v[0] if v else "") for k, v in qs.items() if k.startswith("utm_")}
    except Exception:
        return {}


@router.post("/events", response_model=IngestResult)
def ingest_event(
    body: IngestEvent,
    request: Request,
    key: ApiKey = Depends(require_write_key),
    db: Session = Depends(get_db),
):
    """Single-event server convenience endpoint; shares validation and deduplication."""
    return ingest(IngestBatch(events=[body]), request, key, db)
