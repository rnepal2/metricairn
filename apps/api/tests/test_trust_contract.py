"""Regression tests for tenant, credential, and analytics trust boundaries."""

from datetime import datetime, timedelta, timezone

import pytest
from app.core.database import Base, get_db
from app.main import create_app
from app.models import Event
from app.services import analytics, nl
from app.services.sql_sandbox import execute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def contract(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/contract.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
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


def track(project):
    return {"X-Write-Key": project["write_key"]}


def manage(project):
    return {"X-Management-Key": project["management_key"]}


def test_project_list_is_private_and_scoped(contract):
    client, _, a, b = contract
    assert client.get("/api/v1/projects").status_code == 401
    assert [p["id"] for p in client.get("/api/v1/projects", headers=read(a)).json()] == [a["id"]]
    assert (
        client.get(f"/api/v1/projects/{b['id']}/data/summary", headers=read(a)).status_code == 403
    )


@pytest.mark.parametrize("credential", ["read", "write"])
def test_public_and_read_keys_cannot_administer(contract, credential):
    client, _, a, _ = contract
    key = a[f"{credential}_key"]
    headers = {"X-Management-Key": key, "X-Read-Key": key, "X-Write-Key": key}
    for method, path, body in [
        ("post", f"/api/v1/projects/{a['id']}/notes", {"text": "Fake deploy"}),
        (
            "post",
            "/api/v1/funnels",
            {
                "name": "F",
                "steps": [{"kind": "event", "value": "a"}, {"kind": "event", "value": "b"}],
            },
        ),
        ("post", "/api/v1/alerts/channels", {"kind": "email", "target": "x@example.com"}),
        ("delete", f"/api/v1/projects/{a['id']}/data", None),
    ]:
        assert client.request(method, path, headers=headers, json=body).status_code == 403


def test_management_is_project_scoped(contract):
    client, _, a, b = contract
    assert (
        client.post(
            f"/api/v1/projects/{a['id']}/notes", headers=manage(a), json={"text": "Deploy"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/projects/{b['id']}/notes", headers=manage(a), json={"text": "Deploy"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/ask", headers=read(a), json={"question": "Revenue?", "project_id": b["id"]}
        ).status_code
        == 403
    )


def test_single_event_endpoint_and_idempotency(contract):
    client, factory, a, b = contract
    event = {"name": "revenue", "revenue_amount": 49, "event_id": "order_123"}
    assert (
        client.post("/api/v1/ingest/events", headers=track(a), json=event).json()["accepted"] == 1
    )
    assert (
        client.post("/api/v1/ingest", headers=track(a), json={"events": [event]}).json()["accepted"]
        == 0
    )
    assert (
        client.post("/api/v1/ingest/events", headers=track(b), json=event).json()["accepted"] == 1
    )
    with factory() as db:
        assert db.query(Event).count() == 2


@pytest.mark.parametrize(
    "event",
    [
        {"name": "revenue", "revenue_amount": -1},
        {"name": "signup", "revenue_amount": 12},
        {"name": "revenue", "revenue_currency": "BADCODE"},
        {"name": "revenue", "revenue_currency": "€€€"},
        {"name": "signup", "visitor_id": "v" * 65},
        {"name": "signup", "props": {"huge": "x" * 8193}},
        {"name": "pageview", "at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    ],
)
def test_ingest_rejects_invalid_data(contract, event):
    client, _, a, _ = contract
    assert client.post("/api/v1/ingest/events", headers=track(a), json=event).status_code == 422


def test_bounds_errors_and_cross_origin_ingest(contract):
    client, _, a, _ = contract
    for params in [
        {"metric": "nope"},
        {"date_from": "bad"},
        {"date_from": "2026-10-02", "date_to": "2026-10-01"},
        {"date_from": "2020-01-01"},
    ]:
        assert (
            client.get("/api/v1/query/timeseries", headers=read(a), params=params).status_code
            == 422
        )
    response = client.options(
        "/api/v1/ingest",
        headers={
            "Origin": "https://customer.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Write-Key,Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert (
        client.post("/api/v1/ingest", headers=track(a), content=b"x" * 1_048_577).status_code == 413
    )


def test_half_open_windows_unique_metrics_and_system_exclusion(contract):
    _, factory, a, _ = contract
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with factory() as db:
        for day in [0, 1]:
            db.add(
                Event(
                    project_id=a["id"],
                    name="pageview",
                    visitor_id="v",
                    session_id="s",
                    created_at=start + timedelta(days=day),
                )
            )
        db.add(Event(project_id=a["id"], name="ask", visitor_id="internal", created_at=start))
        db.add(
            Event(
                project_id=a["id"], name="mcp_tool_call", visitor_id="internal2", created_at=start
            )
        )
        db.add(Event(project_id=a["id"], name="signup", visitor_id="v", created_at=start))
        db.add(Event(project_id=a["id"], name="revenue", revenue_amount=25, created_at=start))
        db.commit()
        first = analytics.overview(db, a["id"], start, start + timedelta(days=1))
        whole = analytics.overview(db, a["id"], start, start + timedelta(days=2))
        assert first["pageviews"] == 1 and whole["pageviews"] == 2
        assert whole["visitors"] == 1 and whole["events"] == 1
        assert (
            sum(
                p["value"]
                for p in analytics.timeseries(
                    db, a["id"], "events", start, start + timedelta(days=2)
                )
            )
            == 1
        )
        assert (
            len(analytics.timeseries(db, a["id"], "visitors", start, start + timedelta(days=2)))
            == 2
        )
        assert (
            analytics.compare(db, a["id"], start, start + timedelta(days=1))["metrics"][0][
                "previous"
            ]
            == 0
        )


def test_funnel_counts_later_valid_attempt(contract):
    _, factory, a, _ = contract
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with factory() as db:
        for index, name in enumerate(["signup", "pageview", "signup", "revenue"]):
            db.add(
                Event(
                    project_id=a["id"],
                    name=name,
                    visitor_id="v",
                    path="/pricing",
                    created_at=start + timedelta(minutes=index),
                )
            )
        db.commit()
        steps = [
            {"kind": "page", "value": "/pricing"},
            {"kind": "event", "value": "signup"},
            {"kind": "event", "value": "revenue"},
        ]
        assert [
            row["visitors"]
            for row in analytics.funnel_report(db, a["id"], steps, start, start + timedelta(days=1))
        ] == [1, 1, 1]


def test_money_never_adds_different_currencies(contract):
    _, factory, a, _ = contract
    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc) + timedelta(seconds=1)
    with factory() as db:
        db.add_all(
            [
                Event(
                    project_id=a["id"], name="revenue", revenue_amount=10, revenue_currency="USD"
                ),
                Event(
                    project_id=a["id"], name="revenue", revenue_amount=1000, revenue_currency="JPY"
                ),
            ]
        )
        db.commit()
        usd = analytics.revenue_report(db, a["id"], start, end)
        jpy = analytics.revenue_report(db, a["id"], start, end, currency="JPY")
        assert usd["total"] == 10 and jpy["total"] == 1000
        assert usd["currencies"] == ["JPY", "USD"]
        assert usd["by_source"] == [{"source": "(unattributed)", "revenue": 10}]


@pytest.mark.parametrize(
    "template",
    [
        "SELECT SUM(revenue_amount) FROM events WHERE project_id='{id}' OR 1=1",
        "SELECT SUM(revenue_amount) FROM events WHERE project_id='{id}' UNION ALL SELECT SUM(revenue_amount) FROM events",
        "SELECT SUM(b.revenue_amount) FROM events a JOIN events b ON 1=1 WHERE a.project_id='{id}'",
        "SELECT SUM(revenue_amount) FROM \"events\" WHERE project_id='{id}' OR 1=1",
        "WITH e AS (SELECT * FROM events) SELECT SUM(revenue_amount) FROM e WHERE project_id='{id}' OR 1=1",
    ],
)
def test_sql_execution_cannot_widen_tenant_scope(contract, template):
    _, factory, a, b = contract
    with factory() as db:
        db.add_all(
            [
                Event(project_id=a["id"], name="revenue", revenue_amount=10),
                Event(project_id=b["id"], name="revenue", revenue_amount=999),
            ]
        )
        db.commit()
        result = execute(db, template.format(id=a["id"]), project_id=a["id"])
        assert result["ok"], result
        assert all(row[0] == 10 for row in result["rows"]), result


@pytest.mark.parametrize(
    "sql",
    [
        'SELECT key_hash FROM "api_keys"',
        "SELECT key_hash FROM events, api_keys",
        "SELECT * FROM sqlite_master",
        "SELECT load_extension('/tmp/nope') FROM events",
        "SELECT readfile('/etc/passwd') FROM events",
        "SELECT pg_sleep(10) FROM events",
        "SELECT * INTO stolen FROM events",
    ],
)
def test_sql_denies_other_tables_and_side_effects(contract, sql):
    _, factory, a, _ = contract
    with factory() as db:
        assert not execute(db, sql, project_id=a["id"])["ok"]


def test_unknown_question_without_llm_is_honest(contract):
    client, _, a, _ = contract
    result = client.post(
        "/api/v1/ask", headers=read(a), json={"question": "What is the weather in Paris?"}
    ).json()
    assert any("not a precise answer" in note for note in result["coverage_notes"])


def test_yesterday_is_a_utc_calendar_day():
    plan = nl.heuristic_plan("How many visitors yesterday?")
    start, end = analytics.parse_range(plan["date_from"], plan["date_to"])
    assert end - start == timedelta(days=1)
    assert start.hour == end.hour == 0


def test_key_rotation_and_revocation_do_not_cross_tenants(contract):
    client, _, a, b = contract
    assert client.get("/api/v1/keys", headers=read(a)).status_code == 401
    issued = client.post(
        "/api/v1/keys", headers=manage(a), json={"kind": "read", "name": "New reader"}
    ).json()
    assert issued["key"].startswith("alr_")
    assert (
        client.get("/api/v1/projects/me", headers={"X-Read-Key": issued["key"]}).status_code == 200
    )
    assert client.delete(f"/api/v1/keys/{issued['id']}", headers=manage(b)).status_code == 404
    assert client.delete(f"/api/v1/keys/{issued['id']}", headers=manage(a)).status_code == 200
    assert (
        client.get("/api/v1/projects/me", headers={"X-Read-Key": issued["key"]}).status_code == 403
    )
    inventory = client.get("/api/v1/keys", headers=manage(a)).json()
    assert all("key" not in entry and "key_hash" not in entry for entry in inventory)
    current = next(entry for entry in inventory if entry["scopes"] == "manage")
    assert client.delete(f"/api/v1/keys/{current['id']}", headers=manage(a)).status_code == 409


def test_server_events_without_url_are_not_root_page_visits(contract):
    client, factory, a, _ = contract
    client.post(
        "/api/v1/ingest",
        headers=track(a),
        json={
            "events": [
                {"name": "pageview", "visitor_id": "v", "url": "https://app.test/pricing"},
                {"name": "revenue", "visitor_id": "v", "revenue_amount": 49},
            ]
        },
    )
    rows = client.get(
        "/api/v1/query/breakdown", headers=read(a), params={"dimension": "path"}
    ).json()
    assert [row["value"] for row in rows] == ["/pricing"]
    with factory() as db:
        assert db.query(Event).filter(Event.name == "revenue").one().path == ""


def test_project_provisioning_can_be_gated(contract, monkeypatch):
    from types import SimpleNamespace

    from app.routers import projects

    client, _, _, _ = contract
    monkeypatch.setattr(
        projects, "get_settings", lambda: SimpleNamespace(provisioning_token="operator-token")
    )
    assert client.post("/api/v1/projects", json={"name": "Blocked"}).status_code == 403
    assert (
        client.post(
            "/api/v1/projects", json={"name": "Blocked"}, headers={"X-Provisioning-Token": "wrong"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/projects",
            json={"name": "Allowed"},
            headers={"X-Provisioning-Token": "operator-token"},
        ).status_code
        == 200
    )


def test_anomaly_baseline_keeps_selected_currency(contract):
    from app.services import anomaly

    _, factory, a, _ = contract
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with factory() as db:
        for ago in range(2, 40):
            db.add(
                Event(
                    project_id=a["id"],
                    name="revenue",
                    revenue_amount=49,
                    revenue_currency="EUR",
                    created_at=today - timedelta(days=ago),
                )
            )
            if ago > 7:
                db.add(
                    Event(
                        project_id=a["id"],
                        name="revenue",
                        revenue_amount=1000,
                        revenue_currency="USD",
                        created_at=today - timedelta(days=ago),
                    )
                )
        db.commit()
        flags = [
            flag
            for flag in anomaly.detect(db, a["id"], today - timedelta(days=7), today)
            if flag["metric"] == "revenue"
        ]
        assert flags and all(flag["currency"] == "EUR" for flag in flags)
