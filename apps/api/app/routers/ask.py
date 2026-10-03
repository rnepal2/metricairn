"""Natural-language analytics: POST /api/v1/ask {question}.

Plans the question (LLM when configured, heuristic fallback), executes it against
the analytics service, and returns a human/agent-readable answer plus an optional
chart spec the dashboard renders. Every question is logged as an `ask` event so
the product observes its own agent usage (see /query/mcp-usage).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_read_key
from app.models import ApiKey, Event
from app.schemas import AskOut, AskRequest
from app.services import analytics, anomaly, nl
from app.services.analytics import parse_range

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])


@router.post("", response_model=AskOut)
def ask(body: AskRequest, key: ApiKey = Depends(require_read_key), db: Session = Depends(get_db)):
    plan, planner = nl.plan(body.question)
    project_id = key.project_id
    date_from = plan.get("date_from") or body.date_from
    date_to = plan.get("date_to") or body.date_to
    start, end = parse_range(date_from, date_to)

    action = plan.get("action", "overview")
    answer, data, chart = _execute(db, project_id, action, plan, start, end)

    # Observe our own agent usage (direction-2 analytics).
    db.add(Event(project_id=project_id, name="ask", props={"question": body.question, "planner": planner, "action": action}))
    db.commit()

    return AskOut(answer=answer, data=data, chart=chart, planner=planner)


def _execute(db: Session, project_id: str, action: str, plan: dict, start, end):
    if action == "overview":
        o = analytics.overview(db, project_id, start, end)
        answer = (
            f"{o['visitors']:,} visitors and {o['pageviews']:,} pageviews "
            f"({o['sessions']:,} sessions, {o['bounce_rate']:.0%} bounce). "
            f"{o['events']:,} custom events, {o['revenue']:,.2f} {o['revenue_currency']} revenue."
        )
        return answer, [o], None

    if action == "timeseries_smart":
        metric = plan.get("metric") or ("revenue" if "revenue" in plan.get("question", "").lower() else "visitors")
        if metric not in ("visitors", "pageviews", "sessions", "events", "revenue"):
            metric = "visitors"
        series = analytics.timeseries(db, project_id, metric, start, end)
        total = sum(p["value"] for p in series)
        answer = f"{metric.title()} over the period: {total:,.0f} total across {len(series)} days."
        chart = {"type": "timeseries", "x_key": "t", "y_key": "value", "title": f"{metric.title()} over time"}
        return answer, series, chart

    if action == "breakdown":
        dimension = plan.get("dimension", "path")
        rows = analytics.breakdown(db, project_id, dimension, start, end, limit=10)
        if not rows:
            return f"No {dimension} data in this period.", [], None
        top = rows[0]
        answer = (
            f"Top {dimension}: '{top['value']}' with {top['visitors']:,} visitors "
            f"({top['pageviews']:,} pageviews)."
        )
        chart = {"type": "bar", "x_key": "value", "y_key": "visitors", "title": f"Visitors by {dimension}"}
        return answer, rows, chart

    if action == "revenue":
        r = analytics.revenue_report(db, project_id, start, end)
        answer = (
            f"{r['total']:,.2f} {r['currency']} across {r['transactions']:,} transactions "
            f"({r['revenue_per_visitor']:,.2f} per visitor)."
        )
        chart = {"type": "timeseries", "x_key": "t", "y_key": "value", "title": "Revenue over time"}
        return answer, r["timeseries"], chart

    if action == "revenue_by_source":
        r = analytics.revenue_report(db, project_id, start, end)
        rows = r["by_source"][:10]
        top = rows[0] if rows else {"source": "—", "revenue": 0}
        answer = f"Top revenue source: '{top['source']}' at {top['revenue']:,.2f} {r['currency']}."
        chart = {"type": "bar", "x_key": "source", "y_key": "revenue", "title": "Revenue by source"}
        return answer, rows, chart

    if action == "realtime":
        rt = analytics.realtime(db, project_id)
        answer = f"Right now: {rt['visitors']} visitors, {rt['pageviews']} pageviews in the last {rt['window_minutes']} minutes."
        return answer, [rt], None

    if action == "anomalies":
        found = anomaly.detect(db, project_id, start, end)
        if not found:
            return "No significant anomalies in pageviews or revenue for this period.", [], None
        top = found[0]
        answer = (
            f"{len(found)} anomalies detected. Largest: {top['metric']} {top['direction']} "
            f"on {top['date']} ({top['value']:,.0f} vs ~{top['expected']:,.0f} expected, z={top['z_score']})."
        )
        return answer, found, None

    if action == "funnels":
        from app.models import Funnel

        funnels = db.query(Funnel).filter(Funnel.project_id == project_id).all()
        if not funnels:
            return "No funnels defined yet. Create one in the dashboard under Funnels.", [], None
        rows = []
        for f in funnels:
            steps = analytics.funnel_report(db, project_id, f.steps, start, end)
            overall = steps[-1]["conversion_from_start"] if steps else 0
            rows.append({"funnel": f.name, "overall_conversion": overall, "entered": steps[0]["visitors"] if steps else 0})
        best = max(rows, key=lambda r: r["overall_conversion"])
        answer = f"{len(rows)} funnels. Best converting: '{best['funnel']}' at {best['overall_conversion']:.1%}."
        return answer, rows, None

    if action == "mcp_usage":
        u = analytics.mcp_usage(db, project_id, start, end)
        top = u["by_tool"][0] if u["by_tool"] else {"tool": "—", "calls": 0}
        answer = (
            f"Agents made {u['total_tool_calls']:,} MCP tool calls "
            f"(most used: {top['tool']}, {top['calls']:,} calls) "
            f"and asked {u['questions_asked']:,} natural-language questions."
        )
        return answer, u["by_tool"], None

    o = analytics.overview(db, project_id, start, end)
    return f"{o['visitors']:,} visitors, {o['pageviews']:,} pageviews in this period.", [o], None
