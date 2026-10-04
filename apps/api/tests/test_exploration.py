"""Semantic regressions: filters, conversion denominator, censoring, evidence and isolation."""

from datetime import datetime, timedelta, timezone

import pytest
from app.core.database import Base, get_db
from app.main import create_app
from app.models import Event, Goal, Investigation
from app.services import exploration
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def workspace(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/exploration.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    def sessions():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = sessions
    with TestClient(app) as client:
        a = client.post("/api/v1/projects", json={"name": "A"}).json()
        b = client.post("/api/v1/projects", json={"name": "B"}).json()
        yield client, factory, a, b
    engine.dispose()


def read(project):
    return {"X-Read-Key": project["read_key"]}


def manage(project):
    return {"X-Management-Key": project["management_key"]}


def event(db, project, at, name="pageview", visitor="v", **kw):
    db.add(
        Event(
            project_id=project["id"],
            name=name,
            visitor_id=visitor,
            session_id=visitor,
            created_at=at,
            **kw,
        )
    )


def test_bound_filters_and_distinct_counts(workspace):
    client, factory, a, b = workspace
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    with factory() as db:
        for project, visitor, source in [
            (a, "v", "google"),
            (a, "v", "google"),
            (a, "", "google"),
            (a, "other", "other"),
            (b, "foreign", "google"),
        ]:
            event(db, project, now, visitor=visitor, utm_source=source)
        event(db, a, now, "mcp_tool_call", visitor="internal", utm_source="google")
        db.commit()
    plan = {
        "metric": "visitors",
        "mode": "breakdown",
        "dimension": "device",
        "filters": [{"field": "utm_source", "values": ["google"]}],
    }
    report = client.post("/api/v1/query/run", headers=read(a), json=plan).json()
    assert report["total"] == 1
    assert report["rows"] == [{"value": "(not set)", "count": 1}]
    assert "Distinct identities" in report["notes"][-1]
    plan["metric"] = "pageviews"
    assert client.post("/api/v1/query/run", headers=read(a), json=plan).json()["total"] == 3
    plan["filters"][0]["values"] = ["google' OR 1=1 --"]
    assert client.post("/api/v1/query/run", headers=read(a), json=plan).json()["total"] == 0


@pytest.mark.parametrize(
    "plan",
    [
        {"metric": "event_count"},
        {"metric": "events", "event_name": "signup"},
        {"metric": "event_count", "event_name": "ask"},
        {"mode": "breakdown"},
        {"filters": [{"field": "project_id", "values": ["foreign"]}]},
        {"project_id": "foreign"},
        {"sql": "DROP TABLE events"},
        {"date_from": "nope"},
        {"limit": 0},
    ],
)
def test_invalid_plans_fail_explicitly(workspace, plan):
    client, _, a, _ = workspace
    assert client.post("/api/v1/query/run", headers=read(a), json=plan).status_code == 422


def test_goals_are_unique_visitors_after_entry_not_all_event_visitors(workspace):
    client, factory, a, b = workspace
    assert (
        client.post(
            "/api/v1/goals", headers=read(a), json={"name": "Signup", "event_name": "signup"}
        ).status_code
        == 401
    )
    created = client.post(
        "/api/v1/goals", headers=manage(a), json={"name": "Signup", "event_name": "signup"}
    )
    assert created.status_code == 201
    goal = created.json()
    assert (
        client.post(
            "/api/v1/goals", headers=manage(a), json={"name": "Ask", "event_name": "ask"}
        ).status_code
        == 422
    )
    now = datetime.now(timezone.utc) - timedelta(minutes=10)
    with factory() as db:
        event(db, a, now, "signup", visitor="tooearly")
        event(db, a, now + timedelta(minutes=1), visitor="tooearly")
        event(db, a, now, visitor="converted")
        for i in range(3):
            event(db, a, now + timedelta(minutes=1 + i), "signup", visitor="converted")
        event(db, a, now, "signup", visitor="")
        event(db, a, now, "signup", visitor="noentry")
        event(db, b, now, visitor="foreign")
        db.commit()
    report = client.get(f"/api/v1/goals/{goal['id']}/report", headers=read(a)).json()
    assert report["eligible_visitors"] == 2
    assert report["converted_visitors"] == 1 and report["conversion_rate"] == 0.5
    assert report["occurrences"] == 6 and report["unidentified_occurrences"] == 1
    assert client.get(f"/api/v1/goals/{goal['id']}/report", headers=read(b)).status_code == 404
    assert client.delete(f"/api/v1/goals/{goal['id']}", headers=manage(b)).status_code == 404


def test_retention_first_seen_history_and_right_censoring(workspace):
    _, factory, a, b = workspace
    # Closed fixed weeks, independent of wall-clock test scheduling.
    start = datetime(2025, 1, 6, tzinfo=timezone.utc)
    end = start + timedelta(days=17)
    with factory() as db:
        event(db, a, start - timedelta(days=7), visitor="existing")
        event(db, a, start, visitor="existing")
        event(db, a, start, visitor="new")
        event(db, a, start + timedelta(days=8), "activation", visitor="new")
        event(db, b, start, visitor="foreign")
        event(db, a, start, visitor="")
        db.commit()
        report = exploration.retention(db, a["id"], start, end)
        cohort = report["cohorts"][0]
        assert len(report["cohorts"]) == 1 and cohort["size"] == 1
        assert [cell["visitors"] for cell in cohort["weeks"][:4]] == [1, 1, None, None]
        specific = exploration.retention(db, a["id"], start, end, "activation")
        assert [cell["visitors"] for cell in specific["cohorts"][0]["weeks"][:3]] == [0, 1, None]


def test_investigation_partitions_sum_and_snapshot_does_not_drift(workspace):
    client, factory, a, b = workspace
    end = datetime.now(timezone.utc) - timedelta(minutes=1)
    start = end - timedelta(days=7)
    plan = {"metric": "pageviews", "date_from": start.isoformat(), "date_to": end.isoformat()}
    with factory() as db:
        for index in range(15):
            event(db, a, start - timedelta(days=1), utm_source=f"s{index}")
            for _ in range(index):
                event(db, a, start + timedelta(days=1), utm_source=f"s{index}")
        event(db, b, start + timedelta(days=1), utm_source="foreign")
        db.commit()
    report = client.post("/api/v1/investigations/run", headers=read(a), json=plan).json()
    assert report["current"] == 105 and report["previous"] == 15 and report["change"] == 90
    for segment in report["segments"]:
        assert (
            sum(row["change"] for row in segment["rows"]) + segment["other"]["change"]
            == report["change"]
        )
    result = client.post(
        "/api/v1/investigations", headers=manage(a), json={"title": "Traffic change", "plan": plan}
    )
    assert result.status_code == 201
    saved = result.json()
    with factory() as db:
        event(db, a, start + timedelta(days=1))
        db.commit()
    assert (
        client.get(f"/api/v1/investigations/{saved['id']}", headers=read(a)).json()["evidence"]
        == saved["evidence"]
    )
    assert (
        client.post("/api/v1/investigations/run", headers=read(a), json=plan).json()["current"]
        == 106
    )
    reviewed = client.patch(
        f"/api/v1/investigations/{saved['id']}",
        headers=manage(a),
        json={"status": "resolved", "note": "Validated tracking issue"},
    ).json()
    assert reviewed["evidence"] == saved["evidence"] and reviewed["status"] == "resolved"
    assert client.get(f"/api/v1/investigations/{saved['id']}", headers=read(b)).status_code == 404
    assert (
        client.patch(
            f"/api/v1/investigations/{saved['id']}", headers=manage(b), json={"status": "resolved"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/investigations", headers=read(b)).json() == []
    assert (
        client.patch(
            f"/api/v1/investigations/{saved['id']}",
            headers=manage(a),
            json={"status": "resolved", "evidence": {}},
        ).status_code
        == 422
    )


def test_empty_baseline_caveats_and_deletion(workspace):
    client, factory, a, _ = workspace
    saved = client.post(
        "/api/v1/investigations",
        headers=manage(a),
        json={"title": "Empty", "plan": {"metric": "events"}},
    ).json()
    assert saved["evidence"]["change_pct"] is None
    assert any("zero" in note for note in saved["evidence"]["caveats"])
    client.post("/api/v1/goals", headers=manage(a), json={"name": "Signup", "event_name": "signup"})
    deleted = client.delete(f"/api/v1/projects/{a['id']}/data", headers=manage(a)).json()["deleted"]
    assert deleted["goals"] == 1 and deleted["investigations"] == 1
    with factory() as db:
        assert db.query(Goal).count() == db.query(Investigation).count() == 0


def test_series_totals_truncation_and_half_open_window(workspace):
    client, factory, a, _ = workspace
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    with factory() as db:
        event(db, a, start, "signup", path="/a")
        event(db, a, start + timedelta(days=1), "signup", path="/b")
        event(db, a, end, "signup", path="/excluded")
        db.commit()
    plan = {
        "metric": "event_count",
        "event_name": "signup",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "mode": "timeseries",
    }
    report = client.post("/api/v1/query/run", headers=read(a), json=plan).json()
    assert report["total"] == 2 and [row["count"] for row in report["rows"]] == [1, 1]
    plan.update(mode="breakdown", dimension="path", limit=1)
    report = client.post("/api/v1/query/run", headers=read(a), json=plan).json()
    assert report["truncated"] and len(report["rows"]) == 1 and report["total"] == 2
    assert (
        client.post(
            "/api/v1/investigations/run", headers=read(a), json={"metric": "visitors"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/investigations/run", headers=read(a), json={"date_to": "2099-01-01"}
        ).status_code
        == 422
    )
