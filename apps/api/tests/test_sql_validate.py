"""Tests for the agentic-SQL validation framework and orchestration."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Event
from app.services import sql_agent, sql_validate

PID = "proj_eval"
TEST_DB = "sqlite:///./data/test_sql_validate.db"
DB_PATH = "./data/test_sql_validate.db"


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
    for i in range(6):
        session.add(Event(project_id=PID, name="pageview", visitor_id=f"v{i}",
                          created_at=now - timedelta(days=i)))
    session.add(Event(project_id=PID, name="revenue", visitor_id="v1",
                      revenue_amount=49.0, revenue_currency="USD", created_at=now))
    session.commit()
    yield session
    session.close()


def _window():
    end = datetime.now(timezone.utc)
    return end - timedelta(days=30), end


# ---------- semantic checks ----------

def test_allows_events_only():
    ok, _ = sql_validate.semantic_checks(
        "SELECT COUNT(*) FROM events WHERE project_id = 'proj_eval'", PID)
    assert ok


def test_rejects_unknown_tables():
    ok, reason = sql_validate.semantic_checks(
        "SELECT * FROM users WHERE project_id = 'proj_eval'", PID)
    assert not ok and "users" in reason


def test_rejects_missing_project_scope():
    ok, reason = sql_validate.semantic_checks("SELECT COUNT(*) FROM events", PID)
    assert not ok and "project_id" in reason


def test_rejects_wrong_project_id():
    ok, reason = sql_validate.semantic_checks(
        "SELECT COUNT(*) FROM events WHERE project_id = 'other'", PID)
    assert not ok


def test_allows_cte():
    ok, _ = sql_validate.semantic_checks(
        "WITH d AS (SELECT * FROM events WHERE project_id='proj_eval') "
        "SELECT COUNT(*) FROM d", PID)
    assert ok


# ---------- sanity rules ----------

def test_revenue_question_needs_revenue_refs():
    issues = sql_validate.sanity_issues(
        "how much revenue?", "SELECT COUNT(*) FROM events WHERE project_id='p'")
    assert any("revenue" in i for i in issues)
    issues = sql_validate.sanity_issues(
        "how much revenue?",
        "SELECT SUM(revenue_amount) FROM events WHERE project_id='p' AND name='revenue'")
    assert issues == []


def test_date_question_needs_created_at():
    issues = sql_validate.sanity_issues(
        "signups last week", "SELECT COUNT(*) FROM events WHERE project_id='p'")
    assert any("created_at" in i for i in issues)


# ---------- orchestration ----------

def _scripted(sql_map, narrate_map=None):
    """Fake llm_fn: routes generation calls (system mentions SQL query) and
    narration calls (system mentions answering) to different canned outputs."""
    def fake(system, user):
        if "read-only SQL query" in system:
            for needle, sql in sql_map.items():
                if needle in user:
                    return sql
            return "CANNOT_ANSWER"
        if narrate_map:
            for needle, text in narrate_map.items():
                if needle in user:
                    return text
        return None  # fall back to the deterministic template
    return fake


def test_answer_agentic_success(db):
    start, end = _window()
    llm_fn = _scripted(
        {"how many pageviews":
             f"SELECT COUNT(*) AS n FROM events WHERE project_id='{PID}' AND name='pageview'"},
        narrate_map={"how many pageviews": "There were 6 pageviews in the last 30 days."},
    )
    r = sql_agent.answer_agentic(db, PID, "how many pageviews?", start, end, llm_fn=llm_fn)
    assert r["ok"], r
    assert r["planner"] == "agentic_sql"
    assert "6" in r["answer"]
    assert r["confidence"] >= 0.6


def test_answer_agentic_rejects_malicious_sql(db):
    start, end = _window()
    llm_fn = _scripted({"delete": "DELETE FROM events WHERE project_id='proj_eval'"})
    r = sql_agent.answer_agentic(db, PID, "delete my data", start, end, llm_fn=llm_fn)
    assert not r["ok"]
    # extract_sql refuses non-SELECT before validation even sees it —
    # either way, nothing executes and nothing is deleted.
    assert db.query(Event).count() == 7


def test_answer_agentic_rejects_missing_scope(db):
    start, end = _window()
    llm_fn = _scripted({"others": "SELECT SUM(revenue_amount) FROM events"})
    r = sql_agent.answer_agentic(db, PID, "show me others data", start, end, llm_fn=llm_fn)
    assert not r["ok"]


def test_answer_agentic_handles_execution_error(db):
    start, end = _window()
    llm_fn = _scripted({"bad": f"SELECT nope FROM events WHERE project_id='{PID}'"})
    r = sql_agent.answer_agentic(db, PID, "bad column?", start, end, llm_fn=llm_fn)
    assert not r["ok"]
    assert "failed" in r["reason"]


def test_answer_agentic_low_confidence_empty(db):
    start, end = _window()
    # Revenue question, but the SQL ignores revenue refs AND returns zero rows:
    # two penalties (0.3 + 0.2) → 0.5 < 0.6 → honest failure, not an answer.
    llm_fn = _scripted({
        "revenue last year":
            f"SELECT id FROM events WHERE project_id='{PID}' "
            f"AND created_at < '2000-01-01'",
    })
    r = sql_agent.answer_agentic(db, PID, "revenue last year?", start, end, llm_fn=llm_fn)
    assert not r["ok"]
    assert "low confidence" in r["reason"]


def test_answer_agentic_cannot_answer(db):
    start, end = _window()
    r = sql_agent.answer_agentic(db, PID, "what is the weather?",
                                 start, end, llm_fn=lambda s, u: "CANNOT_ANSWER")
    assert not r["ok"]
