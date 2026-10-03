"""Event ingestion. Write-key scoped to a single project."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_write_key
from app.models import ApiKey, Event
from app.schemas import IngestBatch, IngestResult

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

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
        db.add(
            Event(
                project_id=key.project_id,
                session_id=e.session_id[:64],
                visitor_id=e.visitor_id[:64],
                name=e.name[:200],
                path=(e.url.split("?")[0] if "://" in e.url else e.url)[:1000] or "/",
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
        )
        accepted += 1
    db.commit()
    return IngestResult(accepted=accepted, rejected=len(body.events) - accepted)


def _utm_from_url(url: str) -> dict:
    try:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(url).query)
        return {k: (v[0] if v else "") for k, v in qs.items() if k.startswith("utm_")}
    except Exception:
        return {}
