"""Real PostgreSQL parity and read-only cancellation tests (CI service required)."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from app.core.database import Base
from app.models import Event, Project
from app.services import analytics
from app.services.sql_sandbox import execute
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"), reason="No PostgreSQL test service configured"
)


@pytest.fixture()
def postgres():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        first, other = Project(name="Postgres parity"), Project(name="Postgres other")
        db.add_all([first, other])
        db.commit()
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.add_all(
            [
                Event(
                    project_id=first.id,
                    name="pageview",
                    visitor_id="v",
                    session_id="s",
                    created_at=now,
                ),
                Event(
                    project_id=first.id,
                    name="revenue",
                    revenue_amount=49,
                    revenue_currency="USD",
                    created_at=now,
                ),
                Event(project_id=other.id, name="revenue", revenue_amount=999, created_at=now),
            ]
        )
        db.commit()
        yield db, first, now
        db.delete(first)
        db.delete(other)
        db.commit()
    engine.dispose()


def test_postgres_aggregates_scoping_and_timeouts(postgres):
    db, project, now = postgres
    start, end = now - timedelta(days=1), now + timedelta(minutes=1)
    overview = analytics.overview(db, project.id, start, end)
    assert overview["visitors"] == 1 and overview["revenue"] == 49
    assert (
        sum(row["value"] for row in analytics.timeseries(db, project.id, "revenue", start, end))
        == 49
    )
    result = execute(
        db,
        f"SELECT SUM(revenue_amount) FROM events WHERE project_id='{project.id}' OR 1=1",
        project_id=project.id,
        start=start,
        end=end,
    )
    assert result["ok"] and result["rows"] == [(49.0,)]
    assert not execute(db, "SELECT pg_sleep(10) FROM events", project_id=project.id)["ok"]
    result = execute(
        db,
        "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM cnt) SELECT COUNT(*) FROM cnt",
        timeout_s=0.1,
        project_id=project.id,
    )
    assert not result["ok"] and "timed out" in result["reason"]
    assert db.query(Event).filter(Event.project_id == project.id).count() == 2


def test_postgres_exploration_parity(postgres):
    from app.models import Goal
    from app.services import exploration
    from app.services.exploration import QueryPlan

    db, project, now = postgres
    start, end = now - timedelta(days=1), now + timedelta(minutes=1)
    goal = Goal(project_id=project.id, name="Signup", event_name="signup")
    db.add(goal)
    db.add(
        Event(
            project_id=project.id,
            name="signup",
            visitor_id="v",
            created_at=now + timedelta(seconds=1),
            device="mobile",
        )
    )
    db.commit()
    plan = QueryPlan(
        metric="event_count",
        event_name="signup",
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        mode="timeseries",
        filters=[{"field": "device", "values": ["mobile"]}],
    )
    report = exploration.run_plan(db, project.id, plan)
    assert report["total"] == 1 and sum(row["count"] for row in report["rows"]) == 1
    conversion = exploration.goal_report(db, project.id, goal, start, end)
    assert conversion["converted_visitors"] == conversion["eligible_visitors"] == 1
    cohort = exploration.retention(db, project.id, start, end)
    assert sum(row["size"] for row in cohort["cohorts"]) == 1
    change = exploration.investigate(db, project.id, plan)
    assert change["current"] == 1 and change["previous"] == 0
    for dimension in change["segments"]:
        assert sum(row["change"] for row in dimension["rows"]) + dimension["other"]["change"] == 1
