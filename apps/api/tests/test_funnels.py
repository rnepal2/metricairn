"""Tests for segment-aware funnel reports."""

from datetime import datetime, timedelta, timezone

import pytest
from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import ApiKey, Event, Funnel, Project
from app.services import analytics
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./data/test_funnels.db"


@pytest.fixture()
def db():
    import os

    if os.path.exists("./data/test_funnels.db"):
        os.remove("./data/test_funnels.db")
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
    db.add(
        ApiKey(
            project_id=p.id,
            key_hash=_hash("alw_test"),
            key_prefix="alw_test",
            name="w",
            scopes="write",
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

STEPS = [
    {"kind": "page", "value": "/pricing"},
    {"kind": "event", "value": "signup"},
    {"kind": "event", "value": "revenue"},
]


def _journey(db, project_id, visitor, device, converts):
    """One visitor enters at /pricing on `device`; converts iff `converts`."""
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    db.add(
        Event(
            project_id=project_id,
            name="pageview",
            path="/pricing",
            url="https://acme.test/pricing",
            visitor_id=visitor,
            session_id=visitor,
            device=device,
            created_at=base,
        )
    )
    if converts:
        db.add(
            Event(
                project_id=project_id,
                name="signup",
                visitor_id=visitor,
                session_id=visitor,
                device=device,
                created_at=base + timedelta(minutes=5),
            )
        )
        db.add(
            Event(
                project_id=project_id,
                name="revenue",
                visitor_id=visitor,
                session_id=visitor,
                device=device,
                revenue_amount=10,
                created_at=base + timedelta(minutes=10),
            )
        )
    db.commit()


@pytest.fixture()
def funnel(db, project):
    # 4 mobile visitors, 3 convert (75%); 4 desktop visitors, 1 converts (25%).
    for i in range(4):
        _journey(db, project.id, f"m{i}", "mobile", converts=(i < 3))
    for i in range(4):
        _journey(db, project.id, f"d{i}", "desktop", converts=(i < 1))
    f = Funnel(project_id=project.id, name="Signup → Paid", steps=STEPS)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _range():
    return (
        datetime.now(timezone.utc) - timedelta(days=1),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )


def test_segmented_report_splits_by_device(db, project, funnel):
    start, end = _range()
    segs = analytics.funnel_report_by_segment(db, project.id, STEPS, start, end, "device")
    by_value = {s["value"]: s for s in segs}
    assert set(by_value) == {"mobile", "desktop"}
    assert by_value["mobile"]["visitors"] == 4
    assert by_value["mobile"]["overall_conversion"] == 0.75
    assert by_value["desktop"]["overall_conversion"] == 0.25
    # segment step tables are consistent: mobile step counts [4, 3, 3]
    assert [s["visitors"] for s in by_value["mobile"]["steps"]] == [4, 3, 3]


def test_segmented_report_unknown_dimension(db, project, funnel):
    start, end = _range()
    with pytest.raises(ValueError):
        analytics.funnel_report_by_segment(db, project.id, STEPS, start, end, "nonsense")


def test_segmented_report_caps_segments(db, project, funnel):
    start, end = _range()
    segs = analytics.funnel_report_by_segment(
        db, project.id, STEPS, start, end, "device", max_segments=1
    )
    assert len(segs) == 1
    assert segs[0]["value"] == "mobile"  # more entry visitors... tie broken by order; both 4


def test_plain_report_unchanged(db, project, funnel):
    start, end = _range()
    report = analytics.funnel_report(db, project.id, STEPS, start, end)
    assert [s["visitors"] for s in report] == [8, 4, 4]
    assert report[2]["conversion_from_start"] == 0.5


def test_report_endpoint_with_segment_by(db, project, funnel):
    c = _client(db)
    r = c.get(f"/api/v1/funnels/{funnel.id}/report?segment_by=device", headers=R)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["segment_by"] == "device"
    by_value = {s["value"]: s for s in body["segments"]}
    assert by_value["mobile"]["overall_conversion"] == 0.75
    # overall (unsegmented) still present
    assert body["overall_conversion"] == 0.5


def test_report_endpoint_rejects_bad_dimension(db, project, funnel):
    c = _client(db)
    r = c.get(f"/api/v1/funnels/{funnel.id}/report?segment_by=nonsense", headers=R)
    assert r.status_code == 422


def test_heuristic_plans_funnel_segments():
    from app.services import nl

    p = nl.heuristic_plan("which device converts best in the funnel?")
    assert p["action"] == "funnels"
    assert p["segment_by"] == "device"

    p = nl.heuristic_plan("where does the checkout funnel leak the most?")
    assert p["action"] == "funnels"
    assert p.get("segment_by") is None

    p = nl.heuristic_plan("funnel conversion by utm source")
    assert p["segment_by"] == "utm_source"


def test_ask_funnel_with_segment(db, project, funnel):
    c = _client(db)
    r = c.post(
        "/api/v1/ask", headers=R, json={"question": "which device converts best in the funnel?"}
    )
    assert r.status_code == 200, r.text
    ans = r.json()["answer"]
    assert "mobile" in ans and "75" in ans, ans
    assert r.json()["planner"] == "heuristic"
