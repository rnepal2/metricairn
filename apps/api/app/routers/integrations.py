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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import _hash
from app.models import ApiKey, Event

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

_SIGNATURE_TOLERANCE_S = 300
_HANDLED_TYPES = {
    "checkout.session.completed",
    "invoice.paid",
    "checkout.session.async_payment_succeeded",
}
_ZERO_DECIMAL = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}


def _verify_stripe_signature(raw: bytes, header: str | None, secret: str) -> None:
    """Raise HTTPException unless the Stripe-Signature header is valid."""
    if not header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    parts: dict[str, list[str]] = {}
    for part in header.split(","):
        if "=" in part:
            k, value = part.strip().split("=", 1)
            parts.setdefault(k, []).append(value)
    ts = next(iter(parts.get("t", [])), None)
    signatures = parts.get("v1", [])
    if not ts or not signatures:
        raise HTTPException(status_code=400, detail="Malformed Stripe-Signature header")
    try:
        age = abs(time.time() - int(ts))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Malformed Stripe-Signature timestamp"
        ) from None
    if age > _SIGNATURE_TOLERANCE_S:
        raise HTTPException(status_code=400, detail="Stripe-Signature timestamp too old")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")


def _lookup_write_key(db: Session, key: str | None) -> ApiKey:
    if not key:
        raise HTTPException(status_code=401, detail="Missing ?key=alw_... write key")
    record = (
        db.query(ApiKey).filter(ApiKey.key_hash == _hash(key), ApiKey.revoked.is_(False)).first()
    )
    if not record or "write" not in record.scopes.split(","):
        raise HTTPException(status_code=403, detail="Invalid write key")
    return record


def _amount_from(payload: dict, event_type: str) -> tuple[float, str] | None:
    obj = payload.get("data", {}).get("object", {})
    if event_type.startswith("checkout.session."):
        if obj.get("mode") == "subscription" or obj.get("invoice"):
            return None  # invoice.paid is authoritative for subscription/invoiced checkouts
        if obj.get("payment_status") != "paid":
            return None
        cents, currency = obj.get("amount_total"), obj.get("currency", "")
    elif event_type == "invoice.paid":
        if obj.get("status") != "paid":
            return None
        cents, currency = obj.get("amount_paid"), obj.get("currency", "")
    else:
        return None
    if type(cents) is not int or cents <= 0:
        return None
    currency = str(currency or "").upper()
    if len(currency) != 3 or not currency.isalpha():
        return None
    return cents / (1 if currency in _ZERO_DECIMAL else 100), currency


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Stripe webhook receiver not configured (STRIPE_WEBHOOK_SECRET unset)",
        )
    raw = await request.body()
    _verify_stripe_signature(
        raw, request.headers.get("Stripe-Signature"), settings.stripe_webhook_secret
    )
    key = _lookup_write_key(db, request.query_params.get("key"))

    try:
        payload = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("data"), dict)
        or not isinstance(payload["data"].get("object"), dict)
    ):
        raise HTTPException(status_code=400, detail="Malformed Stripe event")
    event_type = payload.get("type", "")
    event_id = payload.get("id", "")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 128:
        raise HTTPException(status_code=400, detail="Missing or invalid Stripe event id")
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

    obj = payload["data"]["object"]
    payment_id = obj.get("payment_intent") or obj.get("id") or event_id
    dedupe_id = "stripe:" + str(payment_id)
    if len(dedupe_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid payment identifier")
    if (
        db.query(Event.id)
        .filter(Event.project_id == key.project_id, Event.event_id == dedupe_id)
        .first()
    ):
        return {"ok": True, "recorded": False, "reason": "duplicate payment"}
    amount = _amount_from(payload, event_type)
    if amount is None:
        return {"ok": True, "recorded": False, "reason": "no positive amount on event"}
    value, currency = amount
    obj = payload.get("data", {}).get("object", {})

    db.add(
        Event(
            project_id=key.project_id,
            event_id=dedupe_id,
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if (
            not db.query(Event.id)
            .filter(Event.project_id == key.project_id, Event.event_id == dedupe_id)
            .first()
        ):
            raise
        return {"ok": True, "recorded": False, "reason": "duplicate payment"}
    return {"ok": True, "recorded": True, "revenue_amount": value, "revenue_currency": currency}
