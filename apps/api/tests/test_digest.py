"""Tests for the weekly founder digest."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import AlertChannel, ApiKey, DigestSetting, Event, Funnel, Project
from app.services import digest as digest_svc
from app.services import notify

TEST_DB = "sqlite:///./data/test_digest.db"


@pytest.fixture()
def db():
    import os

    if os.path.exists("./data/test_digest.db"):
        os.remove("./data/test_digest.db")
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
    db.add(ApiKey(project_id=p.id, key_hash=_hash("alw_test"), key_prefix="alw_test", name="w", scopes="write"))
    db.add(ApiKey(project_id=p.id, key_hash=_hash("alr_test"), key_prefix="alr_test", name="r", scopes="read"))
    db.commit()
    return p


def _client(db):
    app = create_app()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app)


W = {"X-Write-Key": "alw_test"}
R = {"X-Read-Key": "alr_test"}


def _seed_week(db, project_id, days_ago_start, days_ago_end, visitors_per_day, revenue_per_day):
    n = 0
    for d in range(days_ago_start, days_ago_end - 1, -1):
        for v in range(visitors_per_day):
            n += 1
            db.add(
                Event(
                    project_id=project_id,
                    name="pageview",
                    visitor_id=f"w{n}",
                    session_id=f"s{n}",
                    path="/",
                    created_at=datetime.now(timezone.utc) - timedelta(days=d, hours=2),
                )
            )
        if revenue_per_day:
            db.add(
                Event(
                    project_id=project_id,
                    name="revenue",
                    visitor_id=f"r{d}",
                    session_id=f"rs{d}",
                    revenue_amount=revenue_per_day,
                    revenue_currency="USD",
                    created_at=datetime.now(timezone.utc) - timedelta(days=d, hours=1),
                )
            )
    db.commit()


# ---------- unit: due logic ----------

def test_last_slot_and_is_due():
    # Monday 2026-10-05 12:00 UTC is a slot for weekday=0, hour=12.
    monday = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
    slot = digest_svc.last_slot(monday, 0, 12)
    assert slot == datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    sunday = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
    slot = digest_svc.last_slot(sunday, 0, 12)
    assert slot == datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

    s = DigestSetting(project_id="x", weekday=0, hour_utc=12, last_sent_at=None)
    assert digest_svc.is_due(s, monday) is True

    s.last_sent_at = datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc)
    assert digest_svc.is_due(s, monday) is False  # already sent for this slot

    s.last_sent_at = datetime(2026, 9, 28, 12, 30, tzinfo=timezone.utc)
    assert digest_svc.is_due(s, monday) is True  # last week's send doesn't cover this slot

    # naive datetimes from SQLite are treated as UTC, not crashed on
    s.last_sent_at = datetime(2026, 9, 28, 12, 30)
    assert digest_svc.is_due(s, monday) is True


# ---------- unit: compilation ----------

def test_compile_weekly(db, project):
    # Prior week: 10 visitors/day, $50/day. This week: 20/day, $100/day.
    # (Revenue events carry distinct visitor ids, so they count as visitors too.)
    _seed_week(db, project.id, 13, 7, 10, 50.0)
    _seed_week(db, project.id, 6, 0, 20, 100.0)

    db.add(Funnel(project_id=project.id, name="Signup → Paid",
                  steps=[{"kind": "page", "value": "/"}, {"kind": "event", "value": "signup"}]))
    db.commit()

    out = digest_svc.compile_weekly(db, project.id)
    assert out["stats"]["visitors"] == 147  # 7*20 pageview + 7 revenue visitors
    assert out["stats"]["revenue"] == 700.0
    assert "+100%" in out["body"]  # revenue doubled WoW
    assert "Weekly digest" in out["body"]
    assert "Anomalies" in out["body"]
    assert "Acme" in out["subject"]


def test_compile_weekly_empty_project(db, project):
    out = digest_svc.compile_weekly(db, project.id)
    assert out["stats"]["visitors"] == 0
    assert "n/a" in out["body"]  # WoW undefined on zeros


# ---------- API ----------

def test_digest_settings_crud(db, project):
    c = _client(db)
    r = c.get("/api/v1/digest/settings", headers=R)
    assert r.json()["enabled"] is False  # no setting yet

    r = c.put("/api/v1/digest/settings", headers=W, json={"enabled": True, "weekday": 0, "hour_utc": 12})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True

    r = c.get("/api/v1/digest/settings", headers=R)
    assert r.json()["weekday"] == 0

    r = c.put("/api/v1/digest/settings", headers=W, json={"enabled": True, "weekday": 9, "hour_utc": 12})
    assert r.status_code == 422


def test_digest_preview_and_send(db, project, monkeypatch):
    _seed_week(db, project.id, 7, 1, 5, 20.0)
    db.add(AlertChannel(project_id=project.id, kind="email", target="maya@example.com"))
    db.add(DigestSetting(project_id=project.id, enabled=True, weekday=0, hour_utc=12))
    db.commit()

    c = _client(db)
    r = c.post("/api/v1/digest/preview", headers=R)
    assert r.status_code == 200, r.text
    assert "Weekly digest" in r.json()["body"]

    sent = []
    monkeypatch.setattr(notify, "deliver", lambda *a: sent.append(a) or (True, "mock"))
    r = c.post("/api/v1/digest/send", headers=W)
    assert r.json()["sent"] == 1, r.text
    assert len(sent) == 1
    assert "weekly" in sent[0][2].lower()

    # last_sent_at was recorded
    r = c.get("/api/v1/digest/settings", headers=R)
    assert r.json()["last_sent_at"] is not None


def test_digest_send_requires_enabled(db, project):
    c = _client(db)
    r = c.post("/api/v1/digest/send", headers=W)
    assert r.status_code == 409
