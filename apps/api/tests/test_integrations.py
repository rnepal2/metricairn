"""Tests for the opt-in Stripe webhook receiver."""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import ApiKey, Event, Project
from app.routers import integrations

TEST_DB = "sqlite:///./data/test_integrations.db"
SECRET = "whsec_test_secret"


def _fresh_db():
    import os

    if os.path.exists("./data/test_integrations.db"):
        os.remove("./data/test_integrations.db")
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@pytest.fixture()
def setup(monkeypatch):
    db = _fresh_db()
    p = Project(name="Acme", domain="acme.test")
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(ApiKey(project_id=p.id, key_hash=_hash("alw_test"), key_prefix="alw_test", name="w", scopes="write"))
    db.commit()
    monkeypatch.setattr(integrations, "get_settings",
                        lambda: SimpleNamespace(stripe_webhook_secret=SECRET))
    app = create_app()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app), db, p


def _sign(raw: bytes, ts: int | None = None):
    ts = ts if ts is not None else int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _payload(event_type="checkout.session.completed", event_id="evt_123", cents=4900):
    obj = {"id": "cs_123", "amount_total": cents, "amount_paid": cents, "currency": "usd"}
    return json.dumps({"id": event_id, "type": event_type, "livemode": False,
                       "data": {"object": obj}}).encode()


def _post(client, raw, key="alw_test", headers=None):
    h = {"Stripe-Signature": _sign(raw)}
    if headers:
        h.update(headers)
    return client.post(f"/api/v1/integrations/stripe/webhook?key={key}", content=raw, headers=h)


def test_checkout_completed_becomes_revenue_event(setup):
    client, db, p = setup
    raw = _payload()
    r = _post(client, raw)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": True, "recorded": True, "revenue_amount": 49.0, "revenue_currency": "USD"}
    ev = db.query(Event).filter(Event.project_id == p.id, Event.name == "revenue").one()
    assert ev.revenue_amount == 49.0
    assert ev.props["source"] == "stripe"
    assert ev.props["stripe_event"] == "evt_123"
    # no PII: only Stripe ids and flags may be stored
    assert set(ev.props) <= {"source", "stripe_event", "stripe_object", "livemode"}
    assert "customer" not in json.dumps(ev.props).lower().replace("stripe_object", "")


def test_invoice_paid_becomes_revenue_event(setup):
    client, db, p = setup
    r = _post(client, _payload(event_type="invoice.paid", event_id="evt_456", cents=12000))
    assert r.json()["recorded"] is True
    ev = db.query(Event).filter(Event.url == "stripe:evt_456").one()
    assert ev.revenue_amount == 120.0


def test_retry_is_deduplicated(setup):
    client, db, p = setup
    raw = _payload()
    assert _post(client, raw).json()["recorded"] is True
    second = _post(client, raw).json()
    assert second == {"ok": True, "recorded": False, "reason": "duplicate event id"}
    assert db.query(Event).count() == 1


def test_unhandled_event_type_ignored(setup):
    client, db, p = setup
    r = _post(client, _payload(event_type="customer.created", event_id="evt_x"))
    assert r.json() == {"ok": True, "recorded": False, "reason": "ignored event type customer.created"}
    assert db.query(Event).count() == 0


def test_bad_signature_rejected(setup):
    client, db, p = setup
    raw = _payload()
    r = client.post("/api/v1/integrations/stripe/webhook?key=alw_test", content=raw,
                    headers={"Stripe-Signature": "t=123,v1=deadbeef"})
    assert r.status_code == 400
    assert db.query(Event).count() == 0


def test_stale_timestamp_rejected(setup):
    client, db, p = setup
    raw = _payload()
    old_ts = int(time.time()) - 3600
    r = client.post("/api/v1/integrations/stripe/webhook?key=alw_test", content=raw,
                    headers={"Stripe-Signature": _sign(raw, old_ts)})
    assert r.status_code == 400


def test_wrong_key_rejected(setup):
    client, db, p = setup
    raw = _payload()
    r = _post(client, raw, key="alw_wrong")
    assert r.status_code == 403
    assert db.query(Event).count() == 0


def test_disabled_without_secret(setup, monkeypatch):
    client, db, p = setup
    monkeypatch.setattr(integrations, "get_settings",
                        lambda: SimpleNamespace(stripe_webhook_secret=""))
    r = _post(client, _payload())
    assert r.status_code == 503
