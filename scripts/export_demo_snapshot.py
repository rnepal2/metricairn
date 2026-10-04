#!/usr/bin/env python3
"""Export current simulated demo answers and charts as a self-contained HTML file.

Run from the repository root: uv run python scripts/export_demo_snapshot.py [API_URL] [OUT]
No upload or publication is performed. Every answer is fetched at export time.
"""

from __future__ import annotations

import html
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

READ_KEY = "alr_bw_demo_9f2k7q4x1m8z3d6v"
QUESTIONS = [
    "Why did revenue dip recently?",
    "Which campaigns drove the most revenue?",
    "Where does checkout leak the most?",
]


def svg_series(points: list[dict]) -> str:
    if not points:
        return "<p>No chart data.</p>"
    maximum = max(float(p["value"]) for p in points) or 1
    coordinates = " ".join(
        f"{30 + i * 580 / max(1, len(points) - 1):.1f},{180 - float(p['value']) * 150 / maximum:.1f}"
        for i, p in enumerate(points)
    )
    return f'<svg role="img" aria-label="Simulated daily revenue" viewBox="0 0 640 210"><polyline points="{coordinates}" fill="none" stroke="#0f172a" stroke-width="2"/><text x="30" y="205" font-size="12">{html.escape(points[0]["t"][:10])}</text><text x="500" y="205" font-size="12">{html.escape(points[-1]["t"][:10])}</text></svg>'


def main() -> None:
    api = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "output/billwise-demo.html")
    now = datetime.now(timezone.utc)
    headers = {"X-Read-Key": READ_KEY}
    sections = []
    with httpx.Client(base_url=api, headers=headers, timeout=60, trust_env=False) as client:
        revenue_response = client.get(
            "/api/v1/query/revenue",
            params={
                "date_from": (now - timedelta(days=60)).isoformat(),
                "date_to": now.isoformat(),
            },
        )
        revenue_response.raise_for_status()
        revenue = revenue_response.json()
        for question in QUESTIONS:
            response = client.post("/api/v1/ask", json={"question": question})
            response.raise_for_status()
            answer = response.json()
            evidence = answer.get("based_on", {})
            notes = "".join(
                f"<li>{html.escape(note)}</li>" for note in answer.get("coverage_notes", [])
            )
            sections.append(
                f'<section><h2>{html.escape(question)}</h2><p>{html.escape(answer["answer"])}</p><p class="meta">Planner: {html.escape(answer["planner"])} · {evidence.get("events", 0):,} customer events · UTC window {html.escape(str(evidence.get("date_range", {})))}</p><ul>{notes}</ul></section>'
            )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Metricairn · Billwise simulated demo</title><style>body{{font:16px/1.6 system-ui;color:#0f172a;background:#f8fafc;margin:0}}main{{max-width:850px;margin:auto;padding:32px 20px}}section{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;margin:20px 0}}h1{{line-height:1.2}}h2{{font-size:20px}}.meta,footer{{font-size:12px;color:#475569;overflow-wrap:anywhere}}svg{{width:100%}}</style></head><body><main><h1>Investigate a simulated SaaS business with Metricairn</h1><p>Billwise is fictional. This snapshot contains API-computed answers from simulated events, captured {now.isoformat()}. It demonstrates investigation workflows; it does not prove customer savings or establish the cause of revenue changes.</p><section><h2>Recorded gross revenue · 60 days</h2><p>{revenue["total"]:,.2f} {html.escape(revenue["currency"])} · {revenue["transactions"]:,} positive payment events</p>{svg_series(revenue["timeseries"])}<p class="meta">Answers below use their own disclosed windows (normally 30 days). Currency totals are separate; no FX conversion.</p></section>{"".join(sections)}<footer>Captured local snapshot; no live refresh, publication, or external sharing. Questions and answers are escaped for display.</footer></main></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out.resolve()} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
