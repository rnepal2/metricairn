"""Natural-language analytics: POST /api/v1/ask {question}.

Routing: the heuristic planner classifies the question with a confidence
score. High confidence → the deterministic fast path (ten hand-written
actions: instant, free, exact). Low confidence → the agentic SQL path (the
LLM writes SQL against the fixed event schema, validated before trusted).
When the agentic path fails validation, the answer falls back to the
deterministic best-effort with an honest note — never a fabricated answer.

Every question is logged as an `ask` event so the product observes its own
agent usage (see /query/mcp-usage).
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_read_key
from app.models import ApiKey, Event, Note
from app.schemas import AskOut, AskRequest
from app.services import analytics, anomaly, coverage, nl, sql_agent
from app.services import llm as llm_service
from app.services.analytics import parse_range

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])

# Heuristic confidence at or above this → deterministic fast path.
_DETERMINISTIC_THRESHOLD = 0.7


@router.post("", response_model=AskOut)
def ask(
    body: AskRequest,
    request: Request,
    key: ApiKey = Depends(require_read_key),
    db: Session = Depends(get_db),
):
    plan, planner, confidence = nl.plan(body.question)
    project_id = key.project_id
    if body.project_id and body.project_id != project_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Key does not belong to this project")
    date_from = plan.get("date_from") or body.date_from
    date_to = plan.get("date_to") or body.date_to
    start, end = parse_range(date_from, date_to)
    action = plan.get("action", "overview")

    settings = get_settings()
    # Tests (and future BYO-key flows) inject a scripted LLM via app.state.
    llm_fn = getattr(request.app.state, "llm_fn", None)
    agentic_available = settings.agentic_sql_enabled and (
        llm_service.llm_available() or llm_fn is not None
    )

    agentic_result = None
    if confidence < _DETERMINISTIC_THRESHOLD and agentic_available:
        agentic_result = sql_agent.answer_agentic(
            db, project_id, body.question, start, end, llm_fn=llm_fn
        )
        if agentic_result["ok"]:
            provenance = coverage.based_on(db, project_id, start, end)
            _log_ask(db, project_id, body.question, "agentic_sql", "agentic_sql")
            notes = agentic_result["validation_notes"] + coverage.coverage_notes(
                db, project_id, action, start, end
            )
            return AskOut(
                answer=agentic_result["answer"],
                data=agentic_result["rows"],
                chart=None,
                planner="agentic_sql",
                coverage_notes=notes,
                based_on=provenance,
                sql_hint=agentic_result["sql"],
                validation={
                    "confidence": agentic_result["confidence"],
                    "truncated": agentic_result["truncated"],
                },
            )

    # Deterministic fast path — or honest fallback when the agentic path failed.
    answer, data, chart = _execute(db, project_id, action, plan, start, end)
    notes = coverage.coverage_notes(db, project_id, action, start, end)
    if agentic_result is not None and not agentic_result["ok"]:
        notes = [
            f"Couldn't answer this precisely ({agentic_result['reason']}). "
            "Here's the overall picture instead."
        ] + notes
    provenance = coverage.based_on(db, project_id, start, end)

    if confidence < _DETERMINISTIC_THRESHOLD and agentic_result is None:
        notes.insert(
            0,
            "This question is outside the deterministic query vocabulary. Showing an overview, not a precise answer. Configure an LLM provider for supported SQL questions.",
        )
    _log_ask(db, project_id, body.question, planner, action)
    return AskOut(
        answer=answer,
        data=data,
        chart=chart,
        planner=planner,
        coverage_notes=notes,
        based_on=provenance,
    )


def _log_ask(db: Session, project_id: str, question: str, planner: str, action: str) -> None:
    # Observe our own agent usage (direction-2 analytics).
    db.add(
        Event(
            project_id=project_id,
            name="ask",
            props={"question": question, "planner": planner, "action": action},
        )
    )
    db.commit()


def _execute(db: Session, project_id: str, action: str, plan: dict, start, end):
    if action == "overview":
        o = analytics.overview(db, project_id, start, end)
        answer = (
            f"{o['visitors']:,} visitors and {o['pageviews']:,} pageviews "
            f"({o['sessions']:,} sessions, {o['bounce_rate']:.0%} bounce). "
            f"{o['events']:,} custom events, {o['revenue']:,.2f} {o['revenue_currency']} revenue."
        )
        return answer, [o], None

    if action == "event_count":
        event_name = plan["event_name"]
        from sqlalchemy import distinct, func

        count, visitors = (
            analytics._base_query(db, project_id, start, end)
            .filter(Event.name == event_name)
            .with_entities(func.count(), func.count(distinct(func.nullif(Event.visitor_id, ""))))
            .one()
        )
        return (
            f"{count:,} '{event_name}' events from {visitors:,} identified visitors in this period.",
            [{"event": event_name, "events": count, "visitors": visitors}],
            None,
        )

    if action == "timeseries_smart":
        metric = plan.get("metric") or (
            "revenue" if "revenue" in plan.get("question", "").lower() else "visitors"
        )
        if metric not in ("visitors", "pageviews", "sessions", "events", "revenue"):
            metric = "visitors"
        series = analytics.timeseries(db, project_id, metric, start, end)
        o = analytics.overview(db, project_id, start, end)
        total = o[metric]
        answer = f"{metric.title()} over the period: {total:,.0f} total across {len(series)} daily buckets (unique visitors and sessions are deduplicated over the full period)."
        chart = {
            "type": "timeseries",
            "x_key": "t",
            "y_key": "value",
            "title": f"{metric.title()} over time",
        }
        return answer, series, chart

    if action == "breakdown":
        dimension = plan.get("dimension", "path")
        rows = analytics.breakdown(
            db,
            project_id,
            dimension,
            start,
            end,
            limit=10,
            order_by=plan.get("order_by", "visitors"),
        )
        if plan.get("order_by") == "revenue" and rows:
            cur = analytics.overview(db, project_id, start, end)["revenue_currency"]
            named = [row for row in rows if row["value"] != "(not set)"]
            top = named[0] if named else rows[0]
            answer = f"Highest recorded {cur} revenue by {dimension}: '{top['value']}' at {top['revenue']:,.2f}. Attribution follows event tags, not incremental marketing lift."
            missing = next((row for row in rows if row["value"] == "(not set)"), None)
            if missing:
                answer += f" {missing['revenue']:,.2f} {cur} has no {dimension} tag and cannot be assigned to a named campaign."
            return (
                answer,
                rows,
                {
                    "type": "bar",
                    "x_key": "value",
                    "y_key": "revenue",
                    "title": f"Revenue by {dimension}",
                },
            )
        if not rows:
            return f"No {dimension} data in this period.", [], None
        # "(not set)" is honest data, but the headline should name a real value.
        named = [r for r in rows if r["value"] not in ("(not set)", "")]
        top = named[0] if named else rows[0]
        answer = (
            f"Top {dimension}: '{top['value']}' with {top['visitors']:,} visitors "
            f"({top['pageviews']:,} pageviews)."
        )
        rev_leader = max(named or rows, key=lambda r: r["revenue"])
        if rev_leader["revenue"] > 0 and rev_leader["value"] != top["value"]:
            cur = analytics.overview(db, project_id, start, end)["revenue_currency"]
            answer += (
                f" Top by revenue: '{rev_leader['value']}' at {rev_leader['revenue']:,.2f} {cur}."
            )
        chart = {
            "type": "bar",
            "x_key": "value",
            "y_key": "visitors",
            "title": f"Visitors by {dimension}",
        }
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
            return "No unusual activity flags in pageviews or revenue for this period.", [], None
        top = found[0]
        answer = (
            f"{len(found)} anomalies detected. Largest: {top['metric']} {top['direction']} "
            f"on {top['date']} ({top['value']:,.0f} vs ~{top['expected']:,.0f} expected, z={top['z_score']})."
        )
        return answer, found, None

    if action == "explain":
        return _explain(db, project_id, start, end)

    if action == "funnels":
        from app.models import Funnel

        funnels = db.query(Funnel).filter(Funnel.project_id == project_id).all()
        if not funnels:
            return "No funnels defined yet. Create one in the dashboard under Funnels.", [], None
        segment_by = plan.get("segment_by")
        rows = []
        detail = ""
        for f in funnels:
            steps = analytics.funnel_report(db, project_id, f.steps, start, end)
            overall = steps[-1]["conversion_from_start"] if steps else 0
            rows.append(
                {
                    "funnel": f.name,
                    "overall_conversion": overall,
                    "entered": steps[0]["visitors"] if steps else 0,
                }
            )
            if not detail and len(steps) >= 2:
                leaks = [
                    (steps[i]["step"]["value"], steps[i]["conversion_from_prev"])
                    for i in range(1, len(steps))
                ]
                worst_step, worst_conv = min(leaks, key=lambda x: x[1])
                seq = " → ".join(
                    f"{s['step']['value']} ({s['conversion_from_start']:.1%})" for s in steps
                )
                detail = (
                    f" '{f.name}': {steps[0]['visitors']:,} entered; {seq}. "
                    f"Biggest leak: → {worst_step} ({worst_conv:.1%} step conversion)."
                )
        if segment_by:
            segs = analytics.funnel_report_by_segment(
                db, funnels[0].project_id, funnels[0].steps, start, end, segment_by
            )
            if segs:
                ranked = sorted(segs, key=lambda s: s["overall_conversion"], reverse=True)
                comp = ", ".join(f"{s['value']} {s['overall_conversion']:.1%}" for s in ranked[:5])
                detail += f" By {segment_by}: {comp}."
                rows = [
                    {
                        "segment": s["value"],
                        "visitors": s["visitors"],
                        "overall_conversion": s["overall_conversion"],
                    }
                    for s in ranked
                ]
                best = max(rows, key=lambda r: r["overall_conversion"])
                answer = (
                    f"'{funnels[0].name}' by {segment_by}: highest observed is '{best['segment']}' at {best['overall_conversion']:.1%} ({best['visitors']} entry visitors). Small samples can be unstable."
                    + detail
                )
                return answer, rows, None
        best = max(rows, key=lambda r: r["overall_conversion"])
        answer = (
            f"{len(rows)} funnel(s). Best converting: '{best['funnel']}' at {best['overall_conversion']:.1%}."
            + detail
        )
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


def _explain(db: Session, project_id: str, start, end):
    """Explain the most significant anomaly: detect it, localize the segment
    that moved, check whether demand (traffic) moved with it, and cite any
    timeline notes near the window. Heuristic — the planner is disclosed."""
    found = anomaly.detect(db, project_id, start, end)
    if not found:
        return "No unusual activity flags in pageviews or revenue for this period.", [], None

    dips = [a for a in found if a["direction"] == "dip"]
    a = (dips or found)[0]
    # Expand the headline anomaly across consecutive same-direction days so a
    # multi-day outage reads as one window, not isolated daily flags.
    peers = sorted(
        [x for x in found if x["direction"] == a["direction"] and x["metric"] == a["metric"]],
        key=lambda x: x["date"],
    )
    span = [a["date"]]
    if not a.get("sustained"):
        by_date = {x["date"]: x for x in peers}
        d = datetime.fromisoformat(a["date"])
        while (d - timedelta(days=1)).date().isoformat() in by_date:
            d -= timedelta(days=1)
            span.insert(0, d.date().isoformat())
        d = datetime.fromisoformat(a["date"])
        while (d + timedelta(days=1)).date().isoformat() in by_date:
            d += timedelta(days=1)
            span.append(d.date().isoformat())
    d0 = datetime.fromisoformat(span[0])
    d1 = datetime.fromisoformat(a.get("date_end", span[-1]))
    days = a.get("days", len(span))
    d0_start = d0
    d0_end = d1 + timedelta(days=1)
    base_start, base_end = d0 - timedelta(days=14), d0

    metric_key = "revenue" if a["metric"] == "revenue" else "pageviews"
    currency = a.get("currency") or analytics._currency(db, project_id, start, end)
    unit = currency + " " if metric_key == "revenue" else ""

    def window_total(metric: str, w0, w1) -> float:
        return sum(
            p["value"]
            for p in analytics.timeseries(db, project_id, metric, w0, w1, currency=currency)
        )

    t_total = window_total(metric_key, d0_start, d0_end)
    b_total = window_total(metric_key, base_start, base_end) / 14 * days

    when = f"{span[0]} to {d1.date().isoformat()} ({days} days)" if days > 1 else span[0]
    parts = [
        f"{a['metric'].title()} {a['direction']} {when}: "
        f"{unit}{t_total:,.0f} vs ~{unit}{b_total:,.0f} expected (z={a['z_score']})."
    ]

    if b_total > 0 and t_total <= 0.15 * b_total:
        # Total outage across every segment — the strongest possible signal.
        parts.append(
            "Recorded activity fell sharply overall; inspect instrumentation and segment coverage before concluding an outage."
        )
    else:
        # Localize: which segment's metric moved most vs its own baseline.
        best: tuple | None = None  # (dim, segment, target, delta, baseline)
        for dim in ("device", "browser", "utm_source"):
            tgt = {
                r["value"]: r[metric_key]
                for r in analytics.breakdown(
                    db, project_id, dim, d0_start, d0_end, currency=currency
                )
            }
            base = {
                r["value"]: r[metric_key] / 14 * days
                for r in analytics.breakdown(
                    db, project_id, dim, base_start, base_end, currency=currency
                )
            }
            for seg in tgt.keys() | base.keys():
                tv = tgt.get(seg, 0.0)
                bv = base.get(seg, 0.0)
                delta = tv - bv
                if (
                    best is None
                    or (a["direction"] == "dip" and delta < best[3])
                    or (a["direction"] == "spike" and delta > best[3])
                ):
                    best = (dim, seg, tv, delta, bv)
        if best:
            dim, seg, tv, _delta, bv = best
            verb = (
                "had the largest observed decrease"
                if a["direction"] == "dip"
                else "had the largest observed increase"
            )
            parts.append(
                f"Segment check: {dim} '{seg}' {verb} ({unit}{tv:,.0f} vs ~{unit}{bv:,.0f} normally)."
            )

    # Demand check: did traffic move with the metric?
    if metric_key == "revenue":
        pv_t = window_total("pageviews", d0_start, d0_end)
        pv_b = window_total("pageviews", base_start, base_end) / 14 * days
        if pv_b > 0 and pv_t >= 0.7 * pv_b:
            parts.append(
                f"Pageviews held at {pv_t:,.0f} vs ~{pv_b:,.0f} normally — traffic was fine, "
                "so investigate checkout, payment processing, and revenue instrumentation. These events alone cannot establish the cause."
            )
        elif pv_b > 0:
            parts.append(
                f"Pageviews also fell ({pv_t:,.0f} vs ~{pv_b:,.0f}), so observed traffic declined too — "
                "check campaigns and sources, not just checkout."
            )

    # Timeline notes near the anomaly window often name the cause (deploys, launches).
    notes = (
        db.query(Note)
        .filter(
            Note.project_id == project_id,
            Note.at >= d0 - timedelta(days=2),
            Note.at <= d1 + timedelta(days=2),
        )
        .order_by(Note.at)
        .all()
    )
    if notes:
        parts.append(
            "Timeline notes around that window: "
            + "; ".join(f"'{n.text}' ({n.at.date()})" for n in notes)
            + "."
        )

    return " ".join(parts), found, None
