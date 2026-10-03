"""Backend tests — run with: .venv/bin/pytest -q"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import create_app
from app.models import ApiKey, Event, Project
from app.services import analytics, anomaly, nl
from app.core.security import _hash

TEST_DB = "sqlite:///./data/test.db"


@pytest.fixture()
def db():
    import os

    if os.path.exists("./data/test.db"):
        os.remove("./data/test.db")
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


def _event(db, project_id, name="pageview", visitor="v1", session="s1", path="/", days_ago=0, **kw):
    e = Event(
        project_id=project_id,
        name=name,
        visitor_id=visitor,
        session_id=session,
        path=path,
        url=f"https://acme.test{path}",
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        **kw,
    )
    db.add(e)
    db.commit()
    return e


def test_overview_math(db, project):
    # visitor 1: 3 pageviews in one session (not bounced). visitor 2: 1 pageview (bounced).
    for i in range(3):
        _event(db, project.id, visitor="v1", session="s1", path=f"/p{i}")
    _event(db, project.id, visitor="v2", session="s2", path="/")
    _event(db, project.id, name="signup", visitor="v1", session="s1")
    _event(db, project.id, name="revenue", visitor="v1", session="s1", revenue_amount=49.0, revenue_currency="USD")

    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    o = analytics.overview(db, project.id, start, end)
    assert o["visitors"] == 2
    assert o["pageviews"] == 4
    assert o["sessions"] == 2
    assert o["bounce_rate"] == 0.5
    assert o["events"] == 1  # signup; revenue excluded from events count
    assert o["revenue"] == 49.0


def test_timeseries_buckets(db, project):
    _event(db, project.id, days_ago=2, visitor="a")
    _event(db, project.id, days_ago=2, visitor="b")
    _event(db, project.id, days_ago=0, visitor="c")
    start = datetime.now(timezone.utc) - timedelta(days=3)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    series = analytics.timeseries(db, project.id, "visitors", start, end)
    total = sum(p["value"] for p in series)
    assert total == 3
    assert len(series) >= 3


def test_breakdown_referrer_domain(db, project):
    _event(db, project.id, referrer="https://www.google.com/search?q=x", visitor="a")
    _event(db, project.id, referrer="", visitor="b")
    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    rows = analytics.breakdown(db, project.id, "referrer", start, end)
    by_value = {r["value"]: r for r in rows}
    assert "google.com" in by_value
    assert "(direct)" in by_value


def test_funnel_ordering(db, project):
    # v1 completes all steps in order; v2 skips step 2 (should not count at step 3)
    _event(db, project.id, visitor="v1", session="s1", path="/pricing")
    _event(db, project.id, visitor="v1", session="s1", name="signup")
    _event(db, project.id, visitor="v1", session="s1", name="revenue", revenue_amount=10)
    _event(db, project.id, visitor="v2", session="s2", path="/pricing")
    _event(db, project.id, visitor="v2", session="s2", name="revenue", revenue_amount=10)
    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    steps = [
        {"kind": "page", "value": "/pricing"},
        {"kind": "event", "value": "signup"},
        {"kind": "event", "value": "revenue"},
    ]
    report = analytics.funnel_report(db, project.id, steps, start, end)
    assert [s["visitors"] for s in report] == [2, 1, 1]
    assert report[2]["conversion_from_start"] == 0.5


def test_anomaly_detects_spike(db, project):
    for d in range(10, 0, -1):
        _event(db, project.id, days_ago=d, visitor=f"v{d}")
    for i in range(30):  # spike today
        _event(db, project.id, days_ago=0, visitor=f"spike{i}")
    start = datetime.now(timezone.utc) - timedelta(days=11)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    found = anomaly.detect(db, project.id, start, end, z_threshold=2.0)
    assert found, "expected a spike anomaly"
    assert found[0]["direction"] == "spike"
    assert found[0]["metric"] == "pageviews"


def test_nl_heuristic_plans():
    assert nl.heuristic_plan("what were my top pages last week?")["action"] == "breakdown"
    assert nl.heuristic_plan("where is revenue coming from?")["action"] == "revenue_by_source"
    assert nl.heuristic_plan("any anomalies yesterday?")["action"] == "anomalies"
    assert nl.heuristic_plan("how many visitors did we have?")["action"] == "timeseries_smart"
    assert nl.heuristic_plan("what is happening right now?")["action"] == "realtime"


def _client(db):
    app = create_app()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_ingest_and_query_endpoints(db, project):
    client = _client(db)
    r = client.post(
        "/api/v1/ingest",
        headers={"X-Write-Key": "alw_test"},
        json={"events": [{"name": "pageview", "url": "https://acme.test/?utm_source=google", "visitor_id": "v1", "session_id": "s1"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 1

    r = client.get("/api/v1/query/overview", headers={"X-Read-Key": "alr_test"})
    assert r.status_code == 200
    assert r.json()["visitors"] == 1

    r = client.get("/api/v1/query/breakdown?dimension=utm_source", headers={"X-Read-Key": "alr_test"})
    assert r.json()[0]["value"] == "google"


def test_ask_endpoint(db, project):
    _event(db, project.id, visitor="v1", session="s1", path="/pricing")
    client = _client(db)
    r = client.post(
        "/api/v1/ask", headers={"X-Read-Key": "alr_test"}, json={"question": "what are my top pages?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pricing" in body["answer"]
    assert body["chart"]["type"] == "bar"
