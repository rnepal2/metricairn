"""Tests for data transparency (summary) and deletion."""

from datetime import datetime, timedelta, timezone

from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import ApiKey, Event, Funnel, Note, Project
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./data/test_privacy.db"


def _fresh_db():
    import os

    if os.path.exists("./data/test_privacy.db"):
        os.remove("./data/test_privacy.db")
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed(db):
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
    now = datetime.now(timezone.utc)
    for i in range(5):
        db.add(
            Event(
                project_id=p.id,
                name="pageview",
                path="/",
                visitor_id=f"v{i}",
                created_at=now - timedelta(days=i),
            )
        )
    db.add(
        Event(
            project_id=p.id,
            name="revenue",
            revenue_amount=49.0,
            revenue_currency="USD",
            visitor_id="v9",
            created_at=now,
        )
    )
    db.add(Note(project_id=p.id, text="launched", at=now))
    db.add(
        Funnel(project_id=p.id, name="Signup → Paid", steps=[{"kind": "event", "value": "signup"}])
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


def test_summary_reports_what_we_hold():
    db = _fresh_db()
    p = _seed(db)
    r = _client(db).get(f"/api/v1/projects/{p.id}/data/summary", headers=R)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["events"] == 6
    assert body["revenue_events"] == 1
    assert body["notes"] == 1
    assert body["funnels"] == 1
    assert body["first_event_at"] is not None
    assert body["top_events"][0]["name"] == "pageview"
    assert body["top_events"][0]["count"] == 5


def test_summary_requires_read_key():
    db = _fresh_db()
    p = _seed(db)
    r = _client(db).get(f"/api/v1/projects/{p.id}/data/summary")
    assert r.status_code == 401


def test_delete_removes_everything_but_project_and_keys():
    db = _fresh_db()
    p = _seed(db)
    c = _client(db)
    r = c.delete(f"/api/v1/projects/{p.id}/data", headers=W)
    assert r.status_code == 200, r.text
    deleted = r.json()["deleted"]
    assert deleted["events"] == 6
    assert deleted["notes"] == 1
    assert deleted["funnels"] == 1
    # project + keys survive
    assert db.query(Project).count() == 1
    assert db.query(ApiKey).count() == 2
    # summary now empty
    s = c.get(f"/api/v1/projects/{p.id}/data/summary", headers=R).json()
    assert s["events"] == 0
    assert s["first_event_at"] is None


def test_delete_requires_write_key():
    db = _fresh_db()
    p = _seed(db)
    c = _client(db)
    # no key at all -> 401
    assert c.delete(f"/api/v1/projects/{p.id}/data").status_code == 401
    # read key presented as write key -> 403
    r = c.delete(f"/api/v1/projects/{p.id}/data", headers={"X-Management-Key": "alr_test"})
    assert r.status_code == 403
    assert db.query(Event).count() == 6  # nothing deleted
