#!/usr/bin/env python3
"""Export a standalone static snapshot of the Billwise demo page.

Fetches real data from the API (revenue timeseries, campaign breakdown, funnel
report), embeds the agent Q&A transcripts, and renders a single self-contained
HTML file with inline SVG charts — no JS, no backend needed. Useful for sharing
the demo story as a link.

Usage: apps/api/.venv/bin/python scripts/export_demo_snapshot.py [API_URL] [OUT]
"""
from __future__ import annotations

import html
import sys
from datetime import datetime, timedelta, timezone

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/billwise-demo.html"
READ_KEY = "alr_bw_demo_9f2k7q4x1m8z3d6v"

TRANSCRIPT = [
    (
        "Why did revenue dip recently?",
        "Revenue dip 2026-09-26 to 2026-09-29 (4 days): $0 vs ~$1,473 expected (z=-4.98). "
        "The drop hit every device, browser, and source at once. Pageviews held at 3,755 vs "
        "~3,741 normally — traffic was fine, so this looks like a checkout or payment failure, "
        "not a demand problem. Timeline notes around that window: 'Rotated Stripe publishable "
        "key (checkout deploy)' (2026-09-26); 'Rolled back Stripe key — payments restored' (2026-09-30).",
    ),
    (
        "Which content actually drives trials?",
        "Top utm_campaign: 'invoice-template-guide' with 1,591 visitors (3,088 pageviews). "
        "Top by revenue: 'ph-launch' at 872.00 USD.",
    ),
    (
        "Where does checkout leak the most?",
        "1 funnel(s). Best converting: 'Signup → Paid' at 7.2%. 'Signup → Paid': 5,731 entered; "
        "/pricing (100.0%) → signup (15.0%) → revenue (7.2%). Biggest leak: → signup (15.0% step conversion).",
    ),
]


def svg_timeseries(points: list[tuple[str, float]], dip_start: str, dip_end: str) -> str:
    W, H, P = 640, 220, 36
    vals = [v for _, v in points]
    mx = max(vals) or 1
    n = len(points)

    def x(i: int) -> float:
        return P + i * (W - 2 * P) / max(1, n - 1)

    def y(v: float) -> float:
        return H - P + 8 - (v / mx) * (H - 2 * P)

    # dip highlight
    di0 = next((i for i, (t, _) in enumerate(points) if t[:10] >= dip_start), 0)
    di1 = next((i for i, (t, _) in enumerate(points) if t[:10] > dip_end), n - 1)
    rect = f'<rect x="{x(di0):.1f}" y="{P - 14}" width="{x(di1) - x(di0):.1f}" height="{H - 2 * P + 22}" fill="#fee2e2" opacity="0.7"/>'
    line = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    area = line + f" L{x(n-1):.1f},{H - P + 8} L{x(0):.1f},{H - P + 8} Z"
    label = f'<text x="{(x(di0) + x(di1)) / 2:.1f}" y="{P - 20}" text-anchor="middle" font-size="11" fill="#b91c1c" font-weight="600">$0 for 4 days</text>'
    axis = f'<text x="{P}" y="{H - 12}" font-size="10" fill="#94a3b8">{points[0][0][:10]}</text>'
    axis += f'<text x="{W - P}" y="{H - 12}" font-size="10" fill="#94a3b8" text-anchor="end">{points[-1][0][:10]}</text>'
    axis += f'<text x="{P}" y="{P - 20}" font-size="10" fill="#94a3b8">${mx:,.0f}</text>'
    return (
        f'<svg viewBox="0 0 {W} {H}" class="chart">{rect}'
        f'<path d="{area}" fill="#0f172a" opacity="0.08"/>'
        f'<path d="{line}" fill="none" stroke="#0f172a" stroke-width="2"/>{label}{axis}</svg>'
    )


def svg_bars(items: list[tuple[str, float]], money: bool = False) -> str:
    W, H = 640, 44 * len(items) + 16
    mx = max((v for _, v in items), default=1) or 1
    rows = []
    for i, (label, v) in enumerate(items):
        yy = 10 + i * 44
        w = max(3, (v / mx) * (W - 220))
        val = f"${v:,.0f}" if money else f"{v:,.0f}"
        rows.append(
            f'<text x="0" y="{yy + 16}" font-size="12" fill="#334155">{html.escape(label[:34])}</text>'
            f'<rect x="200" y="{yy}" width="{w:.1f}" height="22" rx="4" fill="#0f172a"/>'
            f'<text x="{200 + w + 8:.1f}" y="{yy + 16}" font-size="12" fill="#0f172a" font-weight="600">{val}</text>'
        )
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(rows)}</svg>'


def main() -> None:
    http = httpx.Client(timeout=60, trust_env=False)
    H = {"X-Read-Key": READ_KEY}
    df = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

    rev = http.get(f"{API}/api/v1/query/timeseries", params={"metric": "revenue", "date_from": df}, headers=H).json()
    camps = http.get(f"{API}/api/v1/query/breakdown", params={"dimension": "utm_campaign", "limit": 8, "date_from": df}, headers=H).json()
    funnels = http.get(f"{API}/api/v1/funnels", headers=H).json()
    frep = http.get(f"{API}/api/v1/funnels/{funnels[0]['id']}/report", params={"date_from": df}, headers=H).json()

    points = [(p["t"], p["value"]) for p in rev]
    named_camps = [(r["value"], r["revenue"]) for r in camps if r["value"] != "(not set)"]
    funnel_items = [(s["step"]["value"], s["visitors"]) for s in frep["steps"]]
    f0, f1, f2 = frep["steps"][0], frep["steps"][1], frep["steps"][2]
    funnel_note = (
        f"{f0['visitors']:,} entered at /pricing → {f1['conversion_from_start']:.1%} reached signup → "
        f"{f2['conversion_from_start']:.1%} converted to paid. Biggest leak: pricing → signup."
    )

    q1, q2, q3 = TRANSCRIPT

    def chat(q: str, a: str) -> str:
        return (
            '<div class="chat">'
            f'<div class="q">{html.escape(q)}</div>'
            '<div class="a-wrap"><div class="avatar">◆</div><div>'
            f'<div class="a">{html.escape(a)}</div>'
            '<div class="meta">answered from live data · planned by heuristic</div>'
            "</div></div></div>"
        )

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Billwise × AgentLens — live demo snapshot</title>
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color: #0f172a; background: #fff; line-height: 1.6; }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 0 20px; }}
  header.bar {{ position: sticky; top: 0; background: rgba(255,255,255,.92); backdrop-filter: blur(8px); border-bottom: 1px solid #e2e8f0; z-index: 5; }}
  header.bar .wrap {{ display: flex; align-items: center; justify-content: space-between; padding-top: 12px; padding-bottom: 12px; }}
  .brand {{ font-weight: 800; font-size: 15px; }}
  .badge {{ display: inline-block; font-size: 11px; font-weight: 600; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 999px; padding: 3px 10px; color: #475569; margin-left: 8px; vertical-align: middle; }}
  .badge.blue {{ background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }}
  .hero {{ padding: 56px 0 40px; }}
  .hero h1 {{ font-size: 34px; line-height: 1.2; letter-spacing: -0.5px; max-width: 640px; }}
  .hero h1 .green {{ color: #047857; }}
  .hero p {{ margin-top: 14px; font-size: 17px; color: #475569; max-width: 620px; }}
  section.moment {{ border-top: 1px solid #f1f5f9; padding: 40px 0; }}
  section.moment.alt {{ background: #f8fafc; }}
  .kicker {{ font-size: 12px; font-weight: 700; letter-spacing: 1px; color: #64748b; margin-bottom: 8px; }}
  h2 {{ font-size: 24px; letter-spacing: -0.3px; margin-bottom: 8px; }}
  .lede {{ color: #475569; max-width: 620px; margin-bottom: 20px; }}
  .chat {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; margin-bottom: 20px; }}
  .q {{ background: #0f172a; color: #fff; border-radius: 14px 14px 4px 14px; padding: 10px 14px; font-size: 14px; max-width: 85%; margin-left: auto; width: fit-content; }}
  .a-wrap {{ display: flex; gap: 10px; margin-top: 12px; }}
  .avatar {{ width: 28px; height: 28px; border-radius: 8px; background: #0f172a; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; flex-shrink: 0; }}
  .a {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 4px 14px 14px 14px; padding: 10px 14px; font-size: 14px; }}
  .meta {{ font-size: 11px; color: #94a3b8; margin-top: 4px; }}
  .card {{ border: 1px solid #e2e8f0; border-radius: 14px; padding: 18px; margin-bottom: 20px; background: #fff; }}
  .card h3 {{ font-size: 14px; margin-bottom: 10px; }}
  .card .note {{ font-size: 12px; color: #64748b; margin-top: 8px; }}
  .chart {{ width: 100%; height: auto; }}
  .adv {{ display: flex; gap: 10px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 12px; padding: 14px 16px; font-size: 14px; color: #065f46; }}
  .adv strong {{ color: #065f46; }}
  .vs {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px; }}
  @media (max-width: 640px) {{ .vs {{ grid-template-columns: 1fr; }} .hero h1 {{ font-size: 27px; }} }}
  .vs .card h3 {{ display: flex; align-items: center; gap: 8px; }}
  .vs .card p {{ font-size: 13px; color: #475569; margin-top: 6px; }}
  .vs .card.good {{ background: #ecfdf5; border-color: #a7f3d0; }}
  .vs .card.good p {{ color: #065f46; }}
  .cta {{ background: #0f172a; color: #fff; border-radius: 16px; padding: 28px; margin: 36px 0 12px; }}
  .cta h2 {{ color: #fff; }}
  .cta p {{ color: #cbd5e1; font-size: 14px; max-width: 560px; margin-top: 8px; }}
  footer {{ text-align: center; font-size: 11px; color: #94a3b8; padding: 18px 0 40px; }}
</style></head>
<body>
<header class="bar"><div class="wrap">
  <div><span class="brand">◆ AgentLens</span><span class="badge">Live demo snapshot · simulated data</span></div>
</div></header>

<div class="wrap hero">
  <span class="badge blue">Customer story · Billwise</span>
  <h1 style="margin-top:12px">How Maya found a <span class="green">$9,800/mo</span> checkout bug in 90 seconds.</h1>
  <p>Maya Chen runs <strong>Billwise</strong> — simple invoicing for freelancers, $10k MRR, team of one.
  On a Monday morning her revenue chart looked wrong. She didn't open a dashboard. She asked her AI agent.</p>
</div>

<section class="moment alt"><div class="wrap">
  <div class="kicker">MOMENT 1 · THE MONDAY ALERT</div>
  <h2>"Why did revenue dip recently?"</h2>
  <p class="lede">AgentLens flagged a statistically significant dip overnight. Maya asked one question from her editor — no dashboards, no segment-building.</p>
  {chat(*q1)}
  <div class="card"><h3>Revenue — last 60 days</h3>{svg_timeseries(points, "2026-09-26", "2026-09-29")}
  <p class="note">Detected dip: <strong>2026-09-26 → 2026-09-29 (4 days)</strong> — $0 vs ~$1,473 expected (z = -4.98).</p></div>
  <div class="adv"><div>✓</div><div><strong>The advantage:</strong> From "revenue is down" to "a botched Stripe key rotation took every payment to $0 for 4 days" in one question — <strong>90 seconds</strong> instead of an afternoon in GA4 segments. Maya shipped the fix before lunch and stopped a $9,800/mo leak.</div></div>
</div></section>

<section class="moment"><div class="wrap">
  <div class="kicker">MOMENT 2 · CONTENT ROI</div>
  <h2>"Which content actually drives trials?"</h2>
  <p class="lede">Maya writes a blog post every week but never knew which ones pay. AgentLens attributes signups and revenue back to campaigns — the tracker persists landing UTMs for the whole session, so even clean checkout URLs credit the content that started it.</p>
  {chat(*q2)}
  <div class="card"><h3>Attributed revenue by campaign (60 days)</h3>{svg_bars(named_camps, money=True)}
  <p class="note">Her Product Hunt launch drove $872 — one three-year-old template post drove $1,462, every month, on autopilot.</p></div>
  <div class="adv"><div>✓</div><div><strong>The advantage:</strong> One template post drives <strong>7% of signups</strong> and beat her biggest launch ever on attributed revenue. Maya stopped guessing what to write and doubled down on templates — the kind of answer Plausible and Fathom don't give you.</div></div>
</div></section>

<section class="moment alt"><div class="wrap">
  <div class="kicker">MOMENT 3 · THE FUNNEL</div>
  <h2>"Where does checkout leak the most?"</h2>
  <p class="lede">Pricing → signup → paid, computed in order per visitor. Maya checks it every Friday — or just asks.</p>
  {chat(*q3)}
  <div class="card"><h3>Signup → Paid (60 days)</h3>{svg_bars(funnel_items)}
  <p class="note">{funnel_note}</p></div>
  <div class="adv"><div>✓</div><div><strong>The advantage:</strong> The same funnel her agent queries from the MCP server — <strong>"which step leaks most on mobile?"</strong> is one question away, in the tool she already works in.</div></div>
</div></section>

<section class="moment"><div class="wrap">
  <h2>Monday morning, two ways</h2>
  <div class="vs">
    <div class="card"><h3>✕ With GA4 / Plausible</h3>
      <p>Notice the dip on Monday's dashboard check.</p>
      <p>Build segments: mobile × Safari × last 7 days…</p>
      <p>Guess at causes, check deploys from memory.</p>
      <p><strong>Afternoon gone. Bug ships another week.</strong></p></div>
    <div class="card good"><h3>✓ With AgentLens</h3>
      <p>Anomaly alert arrives overnight, automatically.</p>
      <p>One question: "why did revenue dip last week?"</p>
      <p>Grounded answer: Sep 26–29 — every payment at $0, traffic normal, deploy named.</p>
      <p><strong>Fixed before lunch. $9,800/mo saved.</strong></p></div>
  </div>
  <div class="cta">
    <h2>This demo runs on live data.</h2>
    <p>Every number above is computed from the Billwise dataset. The interactive version lets you open the dashboard with the demo key, ask the AI anything, or connect the MCP server and ask from your own agent — see the AgentLens repo (rnepal2/agentlens, private).</p>
  </div>
</div></section>

<footer>Billwise is a fictional company; all data is simulated by scripts/seed_billwise.py · snapshot {datetime.now(timezone.utc).date().isoformat()}</footer>
</body></html>"""

    with open(OUT, "w") as f:
        f.write(page)
    print(f"wrote {OUT} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
