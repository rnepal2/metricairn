"""AgentLens MCP server — analytics tools for AI agents.

Read-only by default (10 curated query tools + timeline reading). One write
tool, `add_note`, is available opt-in via AGENTLENS_ENABLE_NOTE_WRITE=1 so a
trusted agent can log deploys and launches to the timeline — which is exactly
what makes future "why did revenue dip?" answers good.

Curated on purpose: ~10 tools instead of 1,000. Small tool surfaces keep agent
context lean and answers fast (see research: PostHog needed a "CLI mode" to work
around context flooding).

Run locally (stdio, for Claude Code / Claude Desktop / Cursor):
    AGENTLENS_API_URL=http://localhost:8000 AGENTLENS_READ_KEY=alr_... python -m agentlens_mcp

Or hosted (streamable HTTP):
    python -m agentlens_mcp --http --port 8001
"""

from __future__ import annotations

import argparse
import json
import os

from mcp.server.fastmcp import FastMCP

from agentlens_mcp.client import AgentLensClient, timed_report

mcp = FastMCP("agentlens")
_client: AgentLensClient | None = None


def client() -> AgentLensClient:
    global _client
    if _client is None:
        _client = AgentLensClient()
        if not _client.read_key:
            raise RuntimeError("AGENTLENS_READ_KEY is not set")
    return _client


@mcp.tool()
def list_metrics() -> str:
    """Catalog of available metrics and dimensions. Start here to discover what you can query."""
    c = client()
    return json.dumps(timed_report(c, "list_metrics", c.metrics_catalog), indent=2)


@mcp.tool()
def query_metrics(metric: str = "visitors", days: int = 30, interval: str = "day") -> str:
    """Time series for a metric. metric: visitors|pageviews|sessions|events|revenue. interval: day|hour."""
    c = client()
    return json.dumps(timed_report(c, "query_metrics", c.timeseries, metric, days, interval), indent=2)


@mcp.tool()
def breakdown(dimension: str = "path", days: int = 30, limit: int = 10) -> str:
    """Top values for a dimension: path, referrer, utm_source, utm_medium, utm_campaign, device, browser, os, country, event."""
    c = client()
    return json.dumps(timed_report(c, "breakdown", c.breakdown, dimension, days, limit), indent=2)


@mcp.tool()
def list_dimension_values(dimension: str = "path", days: int = 30) -> str:
    """Discover which values a dimension actually has (e.g. real page paths, real UTM sources)."""
    c = client()
    return json.dumps(timed_report(c, "list_dimension_values", c.dimension_values, dimension, days), indent=2)


@mcp.tool()
def funnel_report(funnel: str = "", days: int = 30, segment_by: str = "") -> str:
    """Conversion report for a funnel (match by name or id). Steps must be completed in order.
    Pass segment_by (e.g. 'device', 'utm_source') to compare conversion per segment —
    a visitor's segment is the dimension value on their entry-step event."""
    c = client()

    def _run():
        funnels = c.funnels()
        match = next((f for f in funnels if f["id"] == funnel or f["name"].lower() == funnel.lower()), None)
        if not match:
            return {"error": f"funnel {funnel!r} not found", "available": [f["name"] for f in funnels]}
        return c.funnel_report(match["id"], days, segment_by or None)

    return json.dumps(timed_report(c, "funnel_report", _run), indent=2)


@mcp.tool()
def revenue_attribution(days: int = 30) -> str:
    """Revenue total, transactions, revenue-per-visitor, and breakdown by traffic source."""
    c = client()
    return json.dumps(timed_report(c, "revenue_attribution", c.revenue, days), indent=2)


@mcp.tool()
def detect_anomalies(days: int = 30) -> str:
    """Statistically significant spikes/dips in pageviews and revenue (z-score detection)."""
    c = client()
    return json.dumps(timed_report(c, "detect_anomalies", c.anomalies, days), indent=2)


@mcp.tool()
def ask(question: str = "", days: int = 30) -> str:
    """Ask a natural-language question about your analytics, e.g. 'why did revenue dip last Tuesday?'"""
    c = client()
    return json.dumps(timed_report(c, "ask", c.ask, question, days), indent=2)


@mcp.tool()
def integration_health() -> str:
    """Is the instrumentation actually flowing? Checklist: tracker pageviews, revenue events,
    custom events, funnels, recency. Run this first when answers look empty or suspicious —
    most 'wrong' answers are missing data, not wrong analysis."""
    c = client()
    return json.dumps(timed_report(c, "integration_health", c.integration_health), indent=2)


@mcp.tool()
def get_realtime() -> str:
    """Live activity: visitors, pageviews and top pages in the last 30 minutes."""
    c = client()
    return json.dumps(timed_report(c, "get_realtime", c.realtime), indent=2)


@mcp.tool()
def mcp_usage(days: int = 30) -> str:
    """How AI agents are using this MCP server: tool-call counts, error rates, and recent questions."""
    c = client()
    return json.dumps(timed_report(c, "mcp_usage", c.mcp_usage, days), indent=2)


@mcp.tool()
def list_notes() -> str:
    """Timeline annotations: launches, deploys, campaigns the founder (or an agent) logged. Newest first."""
    c = client()
    notes = timed_report(c, "list_notes", c.list_notes)
    return json.dumps(notes, indent=2)


def add_note(text: str = "") -> str:
    """Log a timeline annotation: a deploy, launch, campaign, or pricing change.

    One factual line, e.g. "Deployed new pricing page" or "Launched on Product Hunt".
    Notes appear on dashboard charts and make future "why did revenue dip?" answers
    dramatically better — the agent can cite what changed. Keep it short and factual.
    """
    c = client()
    return json.dumps(timed_report(c, "add_note", c.add_note, text), indent=2)


# The single write capability, off by default: read-only stays the default
# posture, and enabling it is an explicit "I trust my agent to annotate".
if os.environ.get("AGENTLENS_ENABLE_NOTE_WRITE") == "1":
    mcp.tool()(add_note)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="serve over streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.http:
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
