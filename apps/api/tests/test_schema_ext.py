"""Tests for the S2 schema extension: user_id/group_id + ensure_columns migration."""

import os

from app.core.database import Base, ensure_columns, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import ApiKey, Event, Project
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./data/test_schema_ext.db"
DB_PATH = "./data/test_schema_ext.db"


def _fresh():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    os.makedirs("./data", exist_ok=True)
    return create_engine(TEST_DB, connect_args={"check_same_thread": False})


def test_ensure_columns_backfills_on_legacy_table():
    """Simulate a pre-S2 database: events table without user_id/group_id."""
    engine = _fresh()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE events (id VARCHAR(32) PRIMARY KEY, project_id VARCHAR(32), "
                "name VARCHAR(200), created_at DATETIME)"
            )
        )
        conn.execute(
            text("INSERT INTO events (id, project_id, name) VALUES ('e1', 'p1', 'pageview')")
        )
    # Point ensure_columns at this engine via monkeypatched module engine is
    # complex; instead replicate: create_all then ensure_columns on a fresh
    # metadata-bound engine is covered below. Here call the real function
    # against this engine by temporarily swapping.
    import app.core.database as dbmod

    old = dbmod.engine
    dbmod.engine = engine
    try:
        Base.metadata.create_all(bind=engine)  # creates other tables, not events
        ensure_columns()
    finally:
        dbmod.engine = old
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(events)")).fetchall()}
    assert "user_id" in cols and "group_id" in cols
    with engine.begin() as conn:
        idx = {r[1] for r in conn.execute(text("PRAGMA index_list(events)")).fetchall()}
    assert "ix_events_user_id" in idx and "ix_events_group_id" in idx
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id, name, user_id FROM events")).fetchone()
    assert row[0] == "e1" and row[2] is None  # old data intact, new cols NULL


def _seed():
    engine = _fresh()
    Base.metadata.create_all(bind=engine)
    import app.core.database as dbmod

    old = dbmod.engine
    dbmod.engine = engine
    try:
        ensure_columns()
    finally:
        dbmod.engine = old
    S = sessionmaker(bind=engine)
    db = S()
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
            scopes="write",
        )
    )
    db.commit()
    db.close()
    return engine


def test_ingest_stores_user_and_group_ids():
    engine = _seed()
    app = create_app()

    def override():
        db = sessionmaker(bind=engine)()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    c = TestClient(app)
    r = c.post(
        "/api/v1/ingest",
        headers={"X-Write-Key": "alw_test"},
        json={
            "events": [
                {"name": "signup", "user_id": "u_123", "group_id": "acme-corp"},
                {"name": "pageview"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 2
    S = sessionmaker(bind=engine)
    db = S()
    su = db.query(Event).filter(Event.name == "signup").one()
    assert su.user_id == "u_123" and su.group_id == "acme-corp"
    pv = db.query(Event).filter(Event.name == "pageview").one()
    assert pv.user_id is None and pv.group_id is None
    db.close()
