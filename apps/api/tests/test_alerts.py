"""Tests for alert channels, rules, delivery, and the alerting engine."""

from datetime import datetime, timedelta, timezone

import pytest
from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import AlertChannel, AlertDelivery, ApiKey, Event, Project
from app.services import alerting, notify
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./data/test_alerts.db"


@pytest.fixture()
def db():
    import os

    if os.path.exists("./data/test_alerts.db"):
        os.remove("./data/test_alerts.db")
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def project(db):
    p = Project(name="Acme", domain="acme.test")
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(
        ApiKey(
            project_id=p.id,
            key_hash=_hash("alw_test"),
            key_prefix="alw_test",
            name="w",
            scopes="manage",
        )
    )
    db.add(
        ApiKey(
            project_id=p.id,
            key_hash=_hash("alr_test"),
            key_prefix="alr_test",
            name="r",
            scopes="read",
        )
    )
    db.commit()
    return p


def _client(db):
    app = create_app()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app)


W = {"X-Management-Key": "alw_test"}
R = {"X-Read-Key": "alr_test"}


def _revenue_day(db, project_id, days_ago, amount):
    db.add(
        Event(
            project_id=project_id,
            name="revenue",
            visitor_id=f"v{days_ago}",
            session_id=f"s{days_ago}",
            revenue_amount=amount,
            revenue_currency="USD",
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )
    )
    db.commit()


# ---------- unit: rule matching & message formatting ----------


def test_rule_matches():
    a = {"metric": "revenue", "direction": "dip", "z_score": -4.5, "date": "2026-01-01"}
    assert alerting.rule_matches(a, {**alerting.DEFAULT_RULE})
    assert alerting.rule_matches(a, {"metric": "revenue", "direction": "any", "min_z": 2.5})
    assert not alerting.rule_matches(a, {"metric": "pageviews", "direction": "any", "min_z": 2.5})
    assert not alerting.rule_matches(a, {"metric": "any", "direction": "spike", "min_z": 2.5})
    assert not alerting.rule_matches(a, {"metric": "any", "direction": "any", "min_z": 5.0})


def test_format_anomaly_message():
    a = {
        "metric": "revenue",
        "direction": "dip",
        "date": "2026-09-26",
        "date_end": "2026-09-29",
        "value": 0,
        "expected": 1473.0,
        "z_score": -4.98,
    }
    subject, body = notify.format_anomaly_message("Billwise", [a])
    assert "Billwise" in subject
    assert "0.00 USD vs ~1,473.00 USD expected" in body
    subject, body = notify.format_anomaly_message("Billwise", [], test=True)
    assert "test" in subject.lower()


def test_anomaly_key():
    assert (
        alerting.anomaly_key({"metric": "revenue", "direction": "dip", "date": "2026-01-01"})
        == "revenue:dip:2026-01-01"
    )
    assert (
        alerting.anomaly_key(
            {
                "metric": "revenue",
                "direction": "dip",
                "date": "2026-01-01",
                "date_end": "2026-01-03",
            }
        )
        == "revenue:dip:2026-01-01:2026-01-03"
    )


# ---------- API: channels & rules ----------


def test_channel_crud(db, project):
    c = _client(db)
    r = c.post(
        "/api/v1/alerts/channels", headers=W, json={"kind": "email", "target": "maya@example.com"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "email"

    r = c.post(
        "/api/v1/alerts/channels", headers=W, json={"kind": "email", "target": "not-an-email"}
    )
    assert r.status_code == 422
    r = c.post(
        "/api/v1/alerts/channels",
        headers=W,
        json={"kind": "slack", "target": "https://example.com/x"},
    )
    assert r.status_code == 422

    # read key can list but webhook URL is masked
    r = c.post(
        "/api/v1/alerts/channels",
        headers=W,
        json={"kind": "slack", "target": "https://hooks.slack.com/services/T000/B000/SECRET123456"},
    )
    cid = r.json()["id"]
    r = c.get("/api/v1/alerts/channels", headers=R)
    assert r.status_code == 200
    slack = [ch for ch in r.json() if ch["kind"] == "slack"][0]
    assert "hooks.slack.com" not in slack["target"]
    assert "SECRET" not in slack["target"]

    r = c.delete(f"/api/v1/alerts/channels/{cid}", headers=W)
    assert r.json()["ok"] is True
    r = c.get("/api/v1/alerts/channels", headers=R)
    assert len(r.json()) == 1


def test_rule_crud(db, project):
    c = _client(db)
    r = c.post(
        "/api/v1/alerts/rules",
        headers=W,
        json={"name": "Revenue dips", "metric": "revenue", "direction": "dip", "min_z": 3.0},
    )
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = c.get("/api/v1/alerts/rules", headers=R)
    assert len(r.json()) == 1
    r = c.delete(f"/api/v1/alerts/rules/{rid}", headers=W)
    assert r.json()["ok"] is True


def test_test_channel_endpoint(db, project, monkeypatch):
    c = _client(db)
    r = c.post(
        "/api/v1/alerts/channels", headers=W, json={"kind": "email", "target": "maya@example.com"}
    )
    cid = r.json()["id"]
    monkeypatch.setattr(notify, "deliver", lambda *a: (True, "mock"))
    r = c.post(f"/api/v1/alerts/channels/{cid}/test", headers=W)
    assert r.json()["ok"] is True
    r = c.get("/api/v1/alerts/deliveries", headers=R)
    assert r.json()[0]["anomaly_key"] == "test"


# ---------- engine: check_project end to end ----------


def test_check_project_sends_and_respects_cooldown(db, project, monkeypatch):
    # 36 steady days of $100, then 3 days of $0 -> a clear revenue dip.
    for d in range(36, 3, -1):
        _revenue_day(db, project.id, d, 100.0)
    for d in range(3, 0, -1):
        _revenue_day(db, project.id, d, 0.0)

    db.add(AlertChannel(project_id=project.id, kind="email", target="maya@example.com"))
    db.commit()

    sent = []
    monkeypatch.setattr(
        notify, "deliver", lambda kind, target, s, b: sent.append((s, b)) or (True, "mock")
    )

    summary = alerting.check_project(db, project.id)
    assert summary["checked"] is True
    assert summary["sent"] == 1, summary
    assert len(sent) == 1
    assert "dip" in sent[0][1]

    # Second run inside cooldown: skipped, nothing sent.
    summary2 = alerting.check_project(db, project.id)
    assert summary2["sent"] == 0
    assert summary2["skipped"] >= 1
    assert len(sent) == 1

    rows = db.query(AlertDelivery).all()
    assert any(r.status == "sent" for r in rows)
    assert any(r.status == "skipped" for r in rows)


def test_check_project_no_channels(db, project):
    summary = alerting.check_project(db, project.id)
    assert summary["checked"] is False
    assert summary["reason"] == "no enabled channels"
