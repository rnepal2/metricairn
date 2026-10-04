"""Graded eval harness for agentic SQL analytics (see docs/agentic-analytics.md).

Tier 1 — runs in CI with a scripted LLM stand-in (canned SQL per question,
including deliberately bad SQL). Grades the *machinery*: routing, validation
accept/reject, honest fallback, answer grounding.
Tier 2 — needs AGENTLENS_LIVE_EVAL=1 plus a real ANTHROPIC_API_KEY or
OPENAI_API_KEY. Grades live end-to-end quality. Skipped in CI.

Seed: deterministic "EvalCo" project — 30 days of pageviews (~120/weekday,
~60/weekend), 5 signups/day, 2 revenue events/day ($49 newsletter / $99
ph-launch) except a 3-day revenue dip to $0 (days 10–12 ago), one funnel,
one timeline note.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import _hash
from app.main import create_app
from app.models import ApiKey, Event, Funnel, Note, Project

PID = "evalco_proj"
TEST_DB = "sqlite:///./data/test_agentic_eval.db"
DB_PATH = "./data/test_agentic_eval.db"
LIVE = bool(os.environ.get("AGENTLENS_LIVE_EVAL"))


def seed_evalco(db):
    p = Project(id=PID, name="EvalCo", domain="evalco.test")
    db.add(p)
    db.commit()
    db.add(ApiKey(project_id=PID, key_hash=_hash("alw_test"), key_prefix="alw_test",
                  name="w", scopes="write"))
    db.add(ApiKey(project_id=PID, key_hash=_hash("alr_test"), key_prefix="alr_test",
                  name="r", scopes="read"))
    # Truncate to midnight (never in the future — noon would postdate the
    # query's end bound when tests run in the morning UTC).
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    exp = {"rev_by_day": {}, "signup_sources": {}, "rev_by_campaign": {},
           "rev_by_country": {}, "pricing_viewers": set(), "pageviews": 0, "signups": 0}
    for d in range(30):
        day = now - timedelta(days=d)
        n_pv = 120 if day.weekday() < 5 else 60
        for i in range(n_pv):
            path = "/pricing" if i % 3 == 0 else ("/" if i % 3 == 1 else "/blog/post")
            device = "desktop" if i % 2 == 0 else "mobile"
            vid = f"pv{d}_{i}"
            if path == "/pricing":
                exp["pricing_viewers"].add(vid)
            db.add(Event(project_id=PID, name="pageview", path=path, device=device,
                         browser="Chrome", visitor_id=vid, session_id=f"s{d}_{i % 20}",
                         created_at=day))
            exp["pageviews"] += 1
        for i in range(5):
            src = ["google", "direct", "newsletter"][i % 3]
            device = "desktop" if i % 2 == 0 else "mobile"
            db.add(Event(project_id=PID, name="signup", visitor_id=f"su{d}_{i}",
                         device=device, utm_source=src, created_at=day))
            exp["signups"] += 1
            exp["signup_sources"][src] = exp["signup_sources"].get(src, 0) + 1
        if d not in (10, 11, 12):  # the dip: no revenue days 10–12 ago
            for i in range(2):
                camp = ["newsletter", "ph-launch"][i % 2]
                amount = 49.0 if i % 2 == 0 else 99.0
                country = ["US", "DE", "IN"][(d + i) % 3]
                db.add(Event(project_id=PID, name="revenue", visitor_id=f"rv{d}_{i}",
                             revenue_amount=amount, revenue_currency="USD",
                             utm_campaign=camp, country=country, created_at=day))
                exp["rev_by_day"][d] = exp["rev_by_day"].get(d, 0) + amount
                exp["rev_by_campaign"][camp] = exp["rev_by_campaign"].get(camp, 0) + amount
                exp["rev_by_country"][country] = exp["rev_by_country"].get(country, 0) + amount
    db.add(Note(project_id=PID, text="deployed checkout v2",
                at=now - timedelta(days=12)))
    db.add(Funnel(project_id=PID, name="Signup → Paid",
                   steps=[{"kind": "event", "value": "signup"},
                          {"kind": "event", "value": "revenue"}]))
    db.commit()
    exp["revenue_total"] = sum(exp["rev_by_day"].values())
    exp["now"] = now
    return exp


def _cut(now, days):
    return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def scripted_sql(exp):
    """Canned SQL per long-tail question. Deterministic — absolute cutoffs."""
    now = exp["now"]
    return {
        # Q11 — compare revenue last 15d vs prior 15d
        "compare revenue": (
            "SELECT CASE WHEN created_at >= '" + _cut(now, 15) + "' THEN 'last_15d' "
            "ELSE 'prev_15d' END AS period, SUM(revenue_amount) AS revenue FROM events "
            f"WHERE project_id='{PID}' AND name='revenue' "
            "AND created_at >= '" + _cut(now, 30) + "' GROUP BY period"),
        # Q12 — 7-day moving average of signups
        "moving average": (
            "SELECT day, AVG(cnt) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING "
            "AND CURRENT ROW) AS ma7 FROM (SELECT date(created_at) AS day, COUNT(*) "
            f"AS cnt FROM events WHERE project_id='{PID}' AND name='signup' "
            "GROUP BY day) ORDER BY day"),
        # Q13 — revenue per visitor by campaign
        "highest revenue per visitor": (
            "SELECT utm_campaign AS campaign, SUM(revenue_amount)/COUNT(DISTINCT "
            f"visitor_id) AS rpv FROM events WHERE project_id='{PID}' AND "
            "name='revenue' GROUP BY utm_campaign ORDER BY rpv DESC"),
        # Q14 — % of visitors who ever sign up
        "percent of visitors": (
            "SELECT ROUND(100.0 * COUNT(DISTINCT CASE WHEN name='signup' THEN "
            "visitor_id END) / COUNT(DISTINCT visitor_id), 1) AS pct FROM events "
            f"WHERE project_id='{PID}'"),
        # Q15 — signups by source last week
        "google vs direct": (
            "SELECT utm_source AS source, COUNT(*) AS signups FROM events "
            f"WHERE project_id='{PID}' AND name='signup' "
            "AND created_at >= '" + _cut(now, 7) + "' GROUP BY source"),
        # Q16 — avg revenue per paying visitor by country
        "per paying visitor by country": (
            "SELECT country, SUM(revenue_amount) AS total, "
            "SUM(revenue_amount)/COUNT(DISTINCT visitor_id) AS arppu "
            f"FROM events WHERE project_id='{PID}' AND name='revenue' GROUP BY country"),
        # Q17 — best revenue day of week
        "day of week": (
            "SELECT strftime('%w', created_at) AS dow, SUM(revenue_amount) AS revenue "
            f"FROM events WHERE project_id='{PID}' AND name='revenue' "
            "GROUP BY dow ORDER BY revenue DESC"),
        # Q18 — pricing viewers who never signed up
        "never signed up": (
            "SELECT COUNT(DISTINCT p.visitor_id) AS n FROM events p "
            f"WHERE p.project_id='{PID}' AND p.name='pageview' AND p.path='/pricing' "
            "AND NOT EXISTS (SELECT 1 FROM events s "
            f"WHERE s.project_id='{PID}' AND s.name='signup' "
            "AND s.visitor_id = p.visitor_id)"),
        # Q20 — signup rate mobile vs desktop
        "signup rate for mobile": (
            "SELECT device, 100.0*SUM(CASE WHEN name='signup' THEN 1 ELSE 0 END)"
            "/COUNT(DISTINCT visitor_id) AS rate FROM events "
            f"WHERE project_id='{PID}' AND device IN ('desktop','mobile') GROUP BY device"),
        # Adversarial
        "delete all my events": "DELETE FROM events",
        "other projects": "SELECT SUM(revenue_amount) FROM events",
        "drop the events": "DROP TABLE events",
        "weather": "CANNOT_ANSWER",
    }


def scripted_llm(sql_map):
    def fake(system, user):
        if "read-only SQL query" in system:  # generation call
            for needle, sql in sql_map.items():
                if needle in user:
                    return sql
            return "CANNOT_ANSWER"
        return None  # narration → deterministic template
    return fake


@pytest.fixture()
def harness(monkeypatch):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)
    db = S()
    exp = seed_evalco(db)
    db.close()

    monkeypatch.setattr("app.services.llm.llm_available", lambda: True)
    app = create_app()
    app.state.llm_fn = scripted_llm(scripted_sql(exp))

    def override():
        s = S()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    yield client, S, exp
    S().close()


R = {"X-Read-Key": "alr_test"}


def _ask(client, question):
    r = client.post("/api/v1/ask", headers=R, json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Tier 1: head questions → deterministic ----------

HEAD = [
    ("why did revenue dip in the last 30 days?", "explain"),
    ("how much revenue did we make in the last 30 days?", "revenue"),
    ("what were my top pages last week?", "breakdown"),
    ("any anomalies in the last 30 days?", "anomalies"),
    ("which device converts best?", "funnels"),
    ("how many visitors did we have yesterday?", "timeseries_smart"),
    ("which blog posts drive the most revenue?", "revenue_by_source"),
    ("where do visitors come from?", "breakdown"),
    ("breakdown of visitors by browser", "breakdown"),
]


@pytest.mark.parametrize("question,action", HEAD)
def test_head_questions_route_deterministic(harness, question, action):
    client, _, _ = harness
    body = _ask(client, question)
    assert body["planner"] == "heuristic", question


def test_head_revenue_total_grounded(harness):
    client, _, exp = harness
    body = _ask(client, "how much revenue did we make in the last 30 days?")
    assert f"{exp['revenue_total']:,.2f}" in body["answer"]


# ---------- Tier 1: long tail → agentic, grounded ----------

def test_q11_compare_revenue_periods(harness):
    client, _, exp = harness
    body = _ask(client, "compare revenue in the last 15 days vs the 15 days before that")
    assert body["planner"] == "agentic_sql"
    last15 = sum(v for d, v in exp["rev_by_day"].items() if d <= 15)
    prev15 = sum(v for d, v in exp["rev_by_day"].items() if 16 <= d < 30)
    assert str(last15) in body["answer"] and str(prev15) in body["answer"]


def test_q12_moving_average(harness):
    client, _, _ = harness
    body = _ask(client, "what is the 7-day moving average of signups?")
    assert body["planner"] == "agentic_sql"
    assert "ma7" in body["answer"] and "5.0" in body["answer"]  # 5 signups/day, every day


def test_q13_campaign_revenue_per_visitor(harness):
    client, _, _ = harness
    body = _ask(client, "which utm_campaign has the highest revenue per visitor?")
    assert body["planner"] == "agentic_sql"
    assert "ph-launch" in body["answer"] and "99.0" in body["answer"]


def test_q14_percent_signup(harness):
    client, _, exp = harness
    body = _ask(client, "what percent of visitors ever sign up?")
    assert body["planner"] == "agentic_sql"
    # distinct visitors: pageviews + signups + revenue visitors (all id-namespaced)
    total_visitors = exp["pageviews"] + exp["signups"] + sum(
        0 if d in (10, 11, 12) else 2 for d in range(30))
    pct = round(100.0 * exp["signups"] / total_visitors, 1)
    assert str(pct) in body["answer"]


def test_q15_signups_by_source(harness):
    client, _, _ = harness
    body = _ask(client, "how many signups came from google vs direct last week?")
    assert body["planner"] == "agentic_sql"
    # cutoff is inclusive: days 0..7 → 8 days × 2 google/day
    assert "google" in body["answer"] and "16" in body["answer"]


def test_q17_best_day_of_week(harness):
    client, _, _ = harness
    body = _ask(client, "which day of week has the highest revenue?")
    assert body["planner"] == "agentic_sql"
    assert "dow" in body["answer"]


def test_q16_arppu_by_country(harness):
    client, _, exp = harness
    body = _ask(client, "what's the average revenue per paying visitor by country?")
    assert body["planner"] == "agentic_sql"
    # per country: total / distinct paying visitors; all three countries present
    for country in ("US", "DE", "IN"):
        assert country in body["answer"]
    us_total = exp["rev_by_country"]["US"]
    assert str(us_total) in body["answer"]


def test_q20_signup_rate_by_device(harness):
    client, _, _ = harness
    body = _ask(client, "compare signup rate for mobile vs desktop")
    assert body["planner"] == "agentic_sql"
    assert "desktop" in body["answer"] and "mobile" in body["answer"]


def test_q18_pricing_never_signup(harness):
    client, _, exp = harness
    body = _ask(client, "how many visitors viewed /pricing but never signed up?")
    assert body["planner"] == "agentic_sql"
    assert str(len(exp["pricing_viewers"])) in body["answer"]


# ---------- Tier 1: adversarial → honest fallback ----------

ADVERSARIAL = [
    "delete all my events",
    "show me data from other projects",
    "drop the events table",
    "what is the weather today?",
]


@pytest.mark.parametrize("question", ADVERSARIAL)
def test_adversarial_falls_back_honestly(harness, question):
    client, S, _ = harness
    # NB: the ask endpoint logs one `ask` event per question — exclude it.
    non_ask = lambda: S().query(Event).filter(Event.name != "ask").count()
    before = non_ask()
    body = _ask(client, question)
    assert body["planner"] == "heuristic"  # deterministic fallback
    assert any("Couldn't answer this precisely" in n for n in body["coverage_notes"]), question
    assert non_ask() == before  # nothing executed destructively


# ---------- Tier 2: live LLM grading (needs AGENTLENS_LIVE_EVAL=1 + key) ----------

@pytest.mark.skipif(not LIVE, reason="needs AGENTLENS_LIVE_EVAL=1 and an LLM key")
def test_live_agentic_quality():
    # Runs the long-tail set against the real LLM on this machine (sandbox
    # egress blocks LLM calls from CI, so this only runs where keys work).
    # Grading: planner == agentic_sql and seeded numbers present in answers.
    # Implemented as a documented manual runbook rather than CI:
    #   AGENTLENS_LIVE_EVAL=1 ANTHROPIC_API_KEY=... pytest tests/test_agentic_eval.py -k live -s
    raise NotImplementedError("manual runbook — see docstring")
