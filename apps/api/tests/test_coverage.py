"""Tests for integration health checks and ask coverage notes."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import ApiKey, Event, Funnel, Project

TEST_DB = "sqlite:///./data/test_coverage.db"


def _fresh_db():
    import os

    if os.path.exists("./data/test_coverage.db"):
        os.remove("./data/test_coverage.db")
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _project(db):
    p = Project(name="Acme", domain="acme.test")
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(ApiKey(project_id=p.id, key_hash=_hash("alw_test"), key_prefix="alw_test", name="w", scopes="write"))
    db.add(ApiKey(project_id=p.id, key_hash=_hash("alr_test"), key_prefix="alr_test", name="r", scopes="read"))
    db.commit()
    return p


def _event(db, pid, name, days_ago=0.04, **kw):
    db.add(Event(project_id=pid, name=name, visitor_id="v1", session_id="s1",
                 created_at=datetime.now(timezone.utc) - timedelta(days=days_ago), **kw))
    db.commit()


def _client(db):
    app = create_app()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app)


R = {"X-Read-Key": "alr_test"}


def test_health_all_ok_when_flowing():
    db = _fresh_db()
    p = _project(db)
    _event(db, p.id, "pageview")
    _event(db, p.id, "revenue", revenue_amount=49.0)
    _event(db, p.id, "signup")
    db.add(Funnel(project_id=p.id, name="F", steps=[]))
    db.commit()
    body = _client(db).get(f"/api/v1/projects/{p.id}/data/health", headers=R).json()
    by_key = {c["key"]: c["status"] for c in body["checks"]}
    assert by_key == {"tracker": "ok", "revenue": "ok", "custom_events": "ok",
                      "funnels": "ok", "live": "ok", "notes": "warning"}
    assert body["missing"] == []


def test_health_flags_missing_revenue():
    db = _fresh_db()
    p = _project(db)
    _event(db, p.id, "pageview")
    body = _client(db).get(f"/api/v1/projects/{p.id}/data/health", headers=R).json()
    by_key = {c["key"]: c for c in body["checks"]}
    assert by_key["revenue"]["status"] == "missing"
    assert "revenue" in body["missing"]
    assert "revenue answer" in by_key["revenue"]["detail"]


def test_health_empty_project():
    db = _fresh_db()
    p = _project(db)
    body = _client(db).get(f"/api/v1/projects/{p.id}/data/health", headers=R).json()
    assert body["checks"][0]["status"] == "missing"
    assert body["checks"][4]["status"] == "missing"  # live


def test_ask_revenue_question_without_revenue_events_warns():
    db = _fresh_db()
    p = _project(db)
    _event(db, p.id, "pageview")
    r = _client(db).post("/api/v1/ask", headers=R,
                         json={"question": "how much revenue did we make?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["coverage_notes"], "expected a coverage note about missing revenue events"
    assert any("revenue" in n.lower() for n in body["coverage_notes"])


def test_ask_revenue_question_with_revenue_events_no_warning():
    db = _fresh_db()
    p = _project(db)
    _event(db, p.id, "pageview")
    _event(db, p.id, "revenue", revenue_amount=49.0)
    r = _client(db).post("/api/v1/ask", headers=R,
                         json={"question": "how much revenue did we make?"})
    assert r.status_code == 200, r.text
    assert r.json()["coverage_notes"] == []


def test_ask_empty_range_warns():
    db = _fresh_db()
    _project(db)
    r = _client(db).post("/api/v1/ask", headers=R,
                         json={"question": "how many visitors?",
                               "date_from": "2020-01-01", "date_to": "2020-01-31"})
    assert r.status_code == 200, r.text
    assert any("no events at all" in n.lower() for n in r.json()["coverage_notes"])
