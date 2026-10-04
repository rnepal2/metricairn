"""Optional integrations that reduce instrumentation friction.

Stripe webhook receiver (opt-in): when STRIPE_WEBHOOK_SECRET is set, Stripe can
POST payment events here and they become `revenue` events automatically — the
zero-code path to revenue answers. Signature-verified per Stripe's scheme;
deduplicated on Stripe's event id so retries don't double-count.

The project is identified by `?key=alw_...` (Stripe webhooks can't set custom
headers). No PII is stored: only amounts, currency, and Stripe ids.
"""

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import _hash
from app.models import ApiKey, Event

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

_SIGNATURE_TOLERANCE_S = 300
_HANDLED_TYPES = {"checkout.session.completed", "invoice.paid"}


def _verify_stripe_signature(raw: bytes, header: str | None, secret: str) -> None:
    """Raise HTTPException unless the Stripe-Signature header is valid."""
    if not header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts, v1 = parts.get("t"), parts.get("v1")
    if not ts or not v1:
        raise HTTPException(status_code=400, detail="Malformed Stripe-Signature header")
    try:
        age = abs(time.time() - int(ts))
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed Stripe-Signature timestamp")
    if age > _SIGNATURE_TOLERANCE_S:
        raise HTTPException(status_code=400, detail="Stripe-Signature timestamp too old")
    signed = f"{ts}.".encode() + raw
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")


def _lookup_write_key(db: Session, key: str | None) -> ApiKey:
    if not key:
        raise HTTPException(status_code=401, detail="Missing ?key=alw_... write key")
    record = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == _hash(key), ApiKey.revoked.is_(False))
        .first()
    )
    if not record or "write" not in record.scopes.split(","):
        raise HTTPException(status_code=403, detail="Invalid write key")
    return record


def _amount_from(payload: dict, event_type: str) -> tuple[float, str] | None:
    obj = payload.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        cents, currency = obj.get("amount_total"), obj.get("currency", "")
    elif event_type == "invoice.paid":
        cents, currency = obj.get("amount_paid"), obj.get("currency", "")
    else:
        return None
    if not isinstance(cents, int) or cents <= 0:
        return None
    return cents / 100.0, (currency or "").upper()


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Stripe webhook receiver not configured (STRIPE_WEBHOOK_SECRET unset)",
        )
    raw = await request.body()
    _verify_stripe_signature(raw, request.headers.get("Stripe-Signature"), settings.stripe_webhook_secret)
    key = _lookup_write_key(db, request.query_params.get("key"))

    try:
        payload = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("type", "")
    event_id = payload.get("id", "")
    if event_type not in _HANDLED_TYPES:
        return {"ok": True, "recorded": False, "reason": f"ignored event type {event_type}"}

    # Idempotency: Stripe retries deliveries; the event id is the dedupe key.
    seen = (
        db.query(Event.id)
        .filter(
            Event.project_id == key.project_id,
            Event.name == "revenue",
            Event.url == f"stripe:{event_id}",
        )
        .first()
    )
    if seen:
        return {"ok": True, "recorded": False, "reason": "duplicate event id"}

    amount = _amount_from(payload, event_type)
    if amount is None:
        return {"ok": True, "recorded": False, "reason": "no positive amount on event"}
    value, currency = amount
    obj = payload.get("data", {}).get("object", {})

    db.add(
        Event(
            project_id=key.project_id,
            name="revenue",
            url=f"stripe:{event_id}",  # doubles as the idempotency key
            revenue_amount=value,
            revenue_currency=currency,
            props={
                "source": "stripe",
                "stripe_event": event_id,
                "stripe_object": obj.get("id", ""),
                "livemode": payload.get("livemode"),
            },
        )
    )
    db.commit()
    return {"ok": True, "recorded": True, "revenue_amount": value, "revenue_currency": currency}
