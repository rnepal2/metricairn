"""Agentic SQL analytics: an LLM writes SQL against the fixed event schema.

The agent never sees customer databases — only this one documented schema,
which is generated from the SQLAlchemy models so the prompt can't drift from
the code. Callers inject ``llm_fn(system, user) -> str | None``; the default
is the server-side LLM (llm.complete_text). Tests inject scripted stand-ins.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.models import Event
from app.services import llm, sql_sandbox, sql_validate

LlmFn = Callable[[str, str], "str | None"]

_COLUMN_MEANINGS = {
    "id": "row id",
    "project_id": "TENANT SCOPE — every query MUST filter project_id = '<given id>'",
    "session_id": "groups hits into sessions",
    "visitor_id": "stable per-visitor id; COUNT(DISTINCT NULLIF(visitor_id, '')) = visitors",
    "user_id": "nullable; set when the customer identifies the user server-side",
    "group_id": "nullable; B2B account/company id",
    "name": "event name: 'pageview' for page views, else custom ('signup', 'revenue', …)",
    "path": "page path, e.g. '/pricing'",
    "url": "full URL",
    "referrer": "referrer URL (may be empty)",
    "utm_source": "attribution source, e.g. 'google', 'newsletter'",
    "utm_medium": "attribution medium, e.g. 'cpc', 'email'",
    "utm_campaign": "attribution campaign, e.g. 'ph-launch'",
    "device": "'desktop' | 'mobile' | 'tablet'",
    "browser": "e.g. 'Chrome', 'Safari'",
    "os": "e.g. 'macOS', 'Windows'",
    "country": "visitor country",
    "props": "JSON object of customer custom properties",
    "revenue_amount": "set on 'revenue' events; 0 otherwise",
    "revenue_currency": "e.g. 'USD'",
    "created_at": "UTC timestamp of the event",
}

_DIALECT_DATE_DOCS = {
    "sqlite": (
        "Date helpers (SQLite): day bucket: strftime('%Y-%m-%d', created_at); "
        "hour of day: strftime('%H', created_at); day of week 0=Sunday: strftime('%w', created_at); "
        "compare timestamps directly, e.g. created_at >= '2026-09-01'."
    ),
    "postgresql": (
        "Date helpers (Postgres): day bucket: date_trunc('day', created_at); "
        "hour of day: EXTRACT(HOUR FROM created_at); day of week 0=Sunday: EXTRACT(DOW FROM created_at); "
        "compare timestamps directly, e.g. created_at >= '2026-09-01'."
    ),
}


def describe_schema(dialect: str = "sqlite") -> str:
    """DDL-ish documentation of the events table, generated from the models."""
    lines = ["Table events — one row per tracked analytics event:"]
    for col in Event.__table__.columns:
        meaning = _COLUMN_MEANINGS.get(col.name, "")
        lines.append(f"  {col.name} ({col.type}) — {meaning}")
    lines.append(_DIALECT_DATE_DOCS.get(dialect, _DIALECT_DATE_DOCS["sqlite"]))
    return "\n".join(lines)


_SYSTEM_PROMPT = """You write a single read-only SQL query that answers a product-analytics question.

Rules:
1. Output EXACTLY ONE statement: SELECT or WITH ... SELECT. Nothing else.
2. You MUST filter project_id = '{project_id}' in the query.
3. Restrict created_at to the given window unless the question asks otherwise.
4. Read-only: no INSERT/UPDATE/DELETE/DROP/ALTER/CREATE under any circumstance.
5. Prefer clear column aliases (e.g. AS visitors, AS revenue).
6. Aggregate sensibly: visitors = COUNT(DISTINCT NULLIF(visitor_id, '')); revenue = SUM(revenue_amount) WHERE name='revenue'.
7. If the question can't be answered from this schema, output exactly: CANNOT_ANSWER

{schema}
"""


def build_prompts(
    question: str, project_id: str, start, end, dialect: str = "sqlite"
) -> tuple[str, str]:
    system = _SYSTEM_PROMPT.format(project_id=project_id, schema=describe_schema(dialect))
    user = (
        f"Question: {question}\n"
        f"Time window: {start.isoformat()} <= created_at < {end.isoformat()} (UTC). The execution layer enforces these bounds.\n"
        f"project_id to filter: {project_id}\n"
        "SQL:"
    )
    return system, user


def extract_sql(text: str) -> str | None:
    """Pull the SQL out of an LLM response (fenced or raw)."""
    if not text or "CANNOT_ANSWER" in text:
        return None
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = m.group(1).strip() if m else text.strip()
    # Drop any prose lines before the statement starts.
    lines = candidate.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*(SELECT|WITH)\b", line, re.IGNORECASE):
            candidate = "\n".join(lines[i:])
            break
    else:
        return None
    return candidate.rstrip().rstrip(";").strip() or None


def generate_sql(
    question: str, project_id: str, start, end, dialect: str = "sqlite", llm_fn: LlmFn | None = None
) -> str | None:
    """Ask the LLM for SQL. Returns the statement or None."""
    fn = llm_fn or llm.complete_text
    system, user = build_prompts(question, project_id, start, end, dialect)
    try:
        text = fn(system, user)
    except Exception:
        return None
    return extract_sql(text) if text else None


def narrate(
    question: str, columns: list[str], rows: list[tuple], llm_fn: LlmFn | None = None
) -> str:
    """Render executed results deterministically; no second model call or invented claims."""
    return _template_narrate(question, columns, rows)


def _format_rows(columns: list[str], rows: list[tuple], limit: int = 25) -> str:
    out = []
    for r in rows[:limit]:
        out.append(", ".join(f"{c}={v}" for c, v in zip(columns, r)))
    if len(rows) > limit:
        out.append(f"… and {len(rows) - limit} more rows")
    return "\n".join(out) if out else "(no rows)"


def _template_narrate(question: str, columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return f"No data matched '{question}' in this period."
    n = len(rows)
    return f"Based on the data ({n} row{'s' if n != 1 else ''}):\n{_format_rows(columns, rows)}"


def answer_agentic(
    db, project_id: str, question: str, start, end, llm_fn: LlmFn | None = None
) -> dict:
    """Full agentic path: generate SQL → validate → execute → assess →
    narrate. Returns {"ok": True, ...} on success; {"ok": False, "reason": ...}
    when anything fails — the router turns that into an honest fallback,
    never a fabricated answer."""
    dialect = db.get_bind().dialect.name
    sql = generate_sql(question, project_id, start, end, dialect, llm_fn=llm_fn)
    if not sql:
        return {
            "ok": False,
            "planner": "agentic_sql",
            "reason": "couldn't formulate a SQL query for this question",
        }

    from app.services.analytics import revenue_currencies

    currencies = revenue_currencies(db, project_id, start, end)
    if len(currencies) > 1 and "revenue_amount" in sql.lower():
        return {
            "ok": False,
            "planner": "agentic_sql",
            "reason": "Multiple currencies are present. Use the currency selector on Revenue for a reliable total; generated revenue SQL is disabled for mixed-currency projects.",
        }

    assessment = sql_validate.assess(question, sql, project_id)
    if not assessment["ok"]:
        return {
            "ok": False,
            "planner": "agentic_sql",
            "sql": sql,
            "reason": f"generated SQL failed validation: {'; '.join(assessment['issues'])}",
        }

    exec_result = sql_sandbox.execute(db, sql, project_id=project_id, start=start, end=end)
    if not exec_result["ok"]:
        return {
            "ok": False,
            "planner": "agentic_sql",
            "sql": sql,
            "reason": f"query failed: {exec_result['reason']}",
        }

    final = sql_validate.assess_result(assessment, exec_result)
    if final["confidence"] < sql_validate.confidence_threshold():
        return {
            "ok": False,
            "planner": "agentic_sql",
            "sql": sql,
            "reason": (
                f"low confidence ({final['confidence']:.2f}): "
                f"{'; '.join(final['issues']) or 'no specific issue'}"
            ),
        }

    answer = narrate(question, exec_result["columns"], exec_result["rows"])
    return {
        "ok": True,
        "planner": "agentic_sql",
        "answer": answer,
        "sql": sql,
        "columns": exec_result["columns"],
        "rows": [dict(zip(exec_result["columns"], r)) for r in exec_result["rows"]],
        "confidence": final["confidence"],
        "validation_notes": final["issues"],
        "truncated": exec_result["truncated"],
    }
