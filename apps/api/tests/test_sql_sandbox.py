"""Tests for the read-only SQL sandbox."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from app.core.database import Base
from app.models import Event
from app.services.sql_sandbox import execute, validate_shape
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./data/test_sql_sandbox.db"
DB_PATH = "./data/test_sql_sandbox.db"


@pytest.fixture()
def db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)
    session = S()
    now = datetime.now(timezone.utc)
    for i in range(10):
        session.add(
            Event(
                project_id="p1",
                name="pageview",
                visitor_id=f"v{i}",
                created_at=now - timedelta(days=i),
            )
        )
    session.add(
        Event(
            project_id="p1",
            name="revenue",
            visitor_id="v1",
            revenue_amount=49.0,
            revenue_currency="USD",
            created_at=now,
        )
    )
    session.add(
        Event(project_id="p2", name="revenue", visitor_id="x", revenue_amount=999.0, created_at=now)
    )
    session.commit()
    yield session
    session.close()


# ---------- validate_shape ----------


def test_valid_select_and_with():
    ok, _ = validate_shape("SELECT COUNT(*) FROM events WHERE project_id = 'p1'")
    assert ok
    ok, _ = validate_shape("WITH d AS (SELECT 1 AS x) SELECT * FROM d;")
    assert ok


def test_rejects_writes_and_ddl():
    for sql in [
        "DELETE FROM events",
        "INSERT INTO events (id) VALUES ('x')",
        "UPDATE events SET name='x'",
        "DROP TABLE events",
        "ALTER TABLE events ADD COLUMN z TEXT",
        "CREATE INDEX i ON events (name)",
        "EXPLAIN SELECT 1",
    ]:
        ok, reason = validate_shape(sql)
        assert not ok, sql
        assert reason


def test_keyword_inside_literal_is_fine():
    ok, _ = validate_shape("SELECT * FROM events WHERE name = 'drop table'")
    assert ok


def test_rejects_multi_statement_and_comment_injection():
    ok, reason = validate_shape("SELECT 1; SELECT 2")
    assert not ok and "multiple" in reason
    ok, _ = validate_shape("SELECT 1; -- comment\nDROP TABLE events")
    assert not ok
    ok, _ = validate_shape("SELECT * FROM events /* ; */ WHERE project_id='p1'")
    assert ok  # semicolon was inside a comment


def test_rejects_empty():
    assert not validate_shape("")[0]
    assert not validate_shape(None)[0]


# ---------- execute ----------


def test_execute_returns_rows_and_columns(db):
    r = execute(db, "SELECT name, COUNT(*) AS n FROM events WHERE project_id='p1' GROUP BY name")
    assert r["ok"], r
    assert set(r["columns"]) == {"name", "n"}
    by_name = {row[0]: row[1] for row in r["rows"]}
    assert by_name == {"pageview": 10, "revenue": 1}


def test_execute_row_cap(db):
    r = execute(db, "SELECT id FROM events", row_cap=3)
    assert r["ok"]
    assert len(r["rows"]) == 3
    assert r["truncated"] is True


def test_execute_rejects_before_touching_db(db):
    r = execute(db, "DELETE FROM events WHERE project_id='p1'")
    assert not r["ok"]
    assert db.query(Event).count() == 12  # nothing deleted


def test_execute_bad_column_is_failure_not_crash(db):
    r = execute(db, "SELECT nope FROM events WHERE project_id='p1'")
    assert not r["ok"]
    assert "execution failed" in r["reason"]


def test_execute_timeout(db):
    sql = (
        "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt) SELECT COUNT(*) FROM cnt"
    )
    r = execute(db, sql, timeout_s=2)
    assert not r["ok"]
    assert "timed out" in r["reason"]


def test_sql_scope_enforces_window_and_excludes_internal_events(db):
    now = datetime.now(timezone.utc)
    db.add(Event(project_id="p1", name="ask", created_at=now))
    db.commit()
    start, end = now - timedelta(hours=1), now + timedelta(minutes=1)
    result = execute(
        db,
        "SELECT COUNT(*) FROM events WHERE project_id='p1' OR 1=1",
        project_id="p1",
        start=start,
        end=end,
    )
    assert result["ok"], result
    assert result["rows"] == [(2,)]  # today's pageview and revenue only
