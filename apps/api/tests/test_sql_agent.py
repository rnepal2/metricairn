"""Unit tests for the SQL agent: schema docs, extraction, generation, narration."""

from datetime import datetime, timedelta, timezone

from app.models import Event
from app.services import sql_agent


def _window():
    end = datetime.now(timezone.utc)
    return end - timedelta(days=30), end


def test_describe_schema_matches_models():
    """The prompt schema can't drift from the code — it's generated from it."""
    doc = sql_agent.describe_schema("sqlite")
    model_cols = {c.name for c in Event.__table__.columns}
    for name in model_cols:
        assert name in doc, f"column {name} missing from schema docs"
    assert "user_id" in doc and "group_id" in doc
    assert "project_id" in doc
    assert "strftime" in sql_agent.describe_schema("sqlite")
    assert "EXTRACT" in sql_agent.describe_schema("postgresql")


def test_extract_sql_fenced():
    text = "Here you go:\n```sql\nSELECT COUNT(*) FROM events;\n```"
    assert sql_agent.extract_sql(text) == "SELECT COUNT(*) FROM events"


def test_extract_sql_raw_and_prose():
    assert sql_agent.extract_sql("SELECT 1") == "SELECT 1"
    text = "I wrote this query for you:\nSELECT name, COUNT(*) FROM events GROUP BY name"
    assert sql_agent.extract_sql(text) == "SELECT name, COUNT(*) FROM events GROUP BY name"


def test_extract_sql_cannot_answer():
    assert sql_agent.extract_sql("CANNOT_ANSWER") is None
    assert sql_agent.extract_sql("") is None
    assert sql_agent.extract_sql("The weather is nice today") is None


def test_generate_sql_uses_injected_llm():
    start, end = _window()
    fake = lambda system, user: "```sql\nSELECT COUNT(*) AS n FROM events WHERE project_id = 'p1'\n```"
    sql = sql_agent.generate_sql("how many events?", "p1", start, end, llm_fn=fake)
    assert sql == "SELECT COUNT(*) AS n FROM events WHERE project_id = 'p1'"


def test_generate_sql_prompt_scopes_project():
    start, end = _window()
    seen = {}

    def fake(system, user):
        seen["system"] = system
        seen["user"] = user
        return "SELECT 1"

    sql_agent.generate_sql("q?", "proj_9", start, end, llm_fn=fake)
    assert "proj_9" in seen["system"]
    assert "proj_9" in seen["user"]


def test_generate_sql_handles_llm_failure():
    start, end = _window()
    assert sql_agent.generate_sql("q?", "p1", start, end, llm_fn=lambda s, u: None) is None

    def boom(s, u):
        raise RuntimeError("down")

    assert sql_agent.generate_sql("q?", "p1", start, end, llm_fn=boom) is None


def test_narrate_uses_injected_llm():
    fake = lambda system, user: "There were 42 signups."
    out = sql_agent.narrate("how many signups?", ["signups"], [(42,)], llm_fn=fake)
    assert out == "There were 42 signups."


def test_narrate_template_only_presents_rows():
    # No LLM key in test env → deterministic template, no invented numbers.
    out = sql_agent.narrate("compare revenue?", ["month", "revenue"],
                            [("2026-09", 1470.0), ("2026-08", 1320.0)], llm_fn=None)
    assert "1470.0" in out and "1320.0" in out
    assert "2026-09" in out


def test_narrate_template_empty():
    out = sql_agent.narrate("anything?", ["n"], [], llm_fn=None)
    assert "No data matched" in out
