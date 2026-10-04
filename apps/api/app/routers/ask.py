"""Natural-language analytics: POST /api/v1/ask {question}.

Plans the question (LLM when configured, heuristic fallback), executes it against
the analytics service, and returns a human/agent-readable answer plus an optional
chart spec the dashboard renders. Every question is logged as an `ask` event so
the product observes its own agent usage (see /query/mcp-usage).
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_read_key
from app.models import ApiKey, Event, Note
from app.schemas import AskOut, AskRequest
from app.services import analytics, anomaly, coverage, nl
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
    notes = coverage.coverage_notes(db, project_id, action, start, end)
    provenance = coverage.based_on(db, project_id, start, end)

    # Observe our own agent usage (direction-2 analytics).
    db.add(Event(project_id=project_id, name="ask", props={"question": body.question, "planner": planner, "action": action}))
    db.commit()

    return AskOut(answer=answer, data=data, chart=chart, planner=planner, coverage_notes=notes, based_on=provenance)


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
            answer += f" Top by revenue: '{rev_leader['value']}' at {rev_leader['revenue']:,.2f} {cur}."
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
            rows.append({"funnel": f.name, "overall_conversion": overall, "entered": steps[0]["visitors"] if steps else 0})
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
            segs = analytics.funnel_report_by_segment(db, funnels[0].project_id, funnels[0].steps, start, end, segment_by)
            if segs:
                ranked = sorted(segs, key=lambda s: s["overall_conversion"], reverse=True)
                comp = ", ".join(f"{s['value']} {s['overall_conversion']:.1%}" for s in ranked[:5])
                detail += f" By {segment_by}: {comp}."
                rows = [
                    {"segment": s["value"], "visitors": s["visitors"], "overall_conversion": s["overall_conversion"]}
                    for s in ranked
                ]
                best = max(rows, key=lambda r: r["overall_conversion"])
                answer = f"'{funnels[0].name}' by {segment_by}: best is '{best['segment']}' at {best['overall_conversion']:.1%}." + detail
                return answer, rows, None
        best = max(rows, key=lambda r: r["overall_conversion"])
        answer = f"{len(rows)} funnel(s). Best converting: '{best['funnel']}' at {best['overall_conversion']:.1%}." + detail
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
        return "No significant anomalies in pageviews or revenue for this period.", [], None

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
    d0_end = d1 + timedelta(days=1) - timedelta(seconds=1)
    base_start, base_end = d0 - timedelta(days=14), d0 - timedelta(seconds=1)

    metric_key = "revenue" if a["metric"] == "revenue" else "pageviews"
    unit = "$" if metric_key == "revenue" else ""

    def window_total(metric: str, w0, w1) -> float:
        return sum(p["value"] for p in analytics.timeseries(db, project_id, metric, w0, w1))

    t_total = window_total(metric_key, d0_start, d0_end)
    b_total = window_total(metric_key, base_start, base_end) / 14 * days

    when = f"{span[0]} to {span[-1]} ({days} days)" if days > 1 else span[0]
    parts = [
        f"{a['metric'].title()} {a['direction']} {when}: "
        f"{unit}{t_total:,.0f} vs ~{unit}{b_total:,.0f} expected (z={a['z_score']})."
    ]

    if b_total > 0 and t_total <= 0.15 * b_total:
        # Total outage across every segment — the strongest possible signal.
        parts.append("The drop hit every device, browser, and source at once.")
    else:
        # Localize: which segment's metric moved most vs its own baseline.
        best: tuple | None = None  # (dim, segment, target, delta, baseline)
        for dim in ("device", "browser", "utm_source"):
            tgt = {r["value"]: r[metric_key] for r in analytics.breakdown(db, project_id, dim, d0_start, d0_end)}
            base = {
                r["value"]: r[metric_key] / 14 * days
                for r in analytics.breakdown(db, project_id, dim, base_start, base_end)
            }
            for seg, tv in tgt.items():
                bv = base.get(seg, 0.0)
                delta = tv - bv
                if best is None or (a["direction"] == "dip" and delta < best[3]) or (
                    a["direction"] == "spike" and delta > best[3]
                ):
                    best = (dim, seg, tv, delta, bv)
        if best:
            dim, seg, tv, _delta, bv = best
            verb = "drove the drop" if a["direction"] == "dip" else "drove the spike"
            parts.append(f"Segment check: {dim} '{seg}' {verb} ({unit}{tv:,.0f} vs ~{unit}{bv:,.0f} normally).")

    # Demand check: did traffic move with the metric?
    if metric_key == "revenue":
        pv_t = window_total("pageviews", d0_start, d0_end)
        pv_b = window_total("pageviews", base_start, base_end) / 14 * days
        if pv_b > 0 and pv_t >= 0.7 * pv_b:
            parts.append(
                f"Pageviews held at {pv_t:,.0f} vs ~{pv_b:,.0f} normally — traffic was fine, "
                "so this looks like a checkout or payment failure, not a demand problem."
            )
        elif pv_b > 0:
            parts.append(
                f"Pageviews also fell ({pv_t:,.0f} vs ~{pv_b:,.0f}), so demand dropped too — "
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
        parts.append("Timeline notes around that window: " + "; ".join(f"'{n.text}' ({n.at.date()})" for n in notes) + ".")

    return " ".join(parts), found, None
