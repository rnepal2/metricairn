# MCP Setup

The AgentLens MCP server is **read-only by default** — your agent queries
analytics but never modifies them. One write tool, `add_note`, is available
opt-in (see below) so a trusted agent can log deploys and launches to the
timeline — which is exactly what makes future "why did revenue dip?" answers
good.

## Install

```bash
cd apps/mcp-server
pip install -e .
```

## Configure

```bash
export AGENTLENS_API_URL="http://localhost:8000"   # or your hosted API
export AGENTLENS_READ_KEY="alr_..."                # from POST /api/v1/projects
export AGENTLENS_WRITE_KEY="alw_..."               # optional: enables self-usage reporting
export AGENTLENS_ENABLE_NOTE_WRITE=1               # optional: enables the add_note tool
```

Claude Code: `claude mcp add --transport stdio agentlens -- python -m agentlens_mcp`
Claude Desktop / Cursor: add to MCP config — see `skills/agentlens-analytics/examples/mcp-config.json`.

Hosted mode: `python -m agentlens_mcp --http --port 8001` (streamable HTTP).

## Tools (11 read, curated + 1 opt-in write)

`list_metrics` · `query_metrics` · `breakdown` · `list_dimension_values` ·
`funnel_report` · `revenue_attribution` · `detect_anomalies` · `ask` ·
`get_realtime` · `mcp_usage` · `list_notes` (+ `add_note` when
`AGENTLENS_ENABLE_NOTE_WRITE=1`)

Full reference: `skills/agentlens-analytics/references/tools.md`.

## Agent-written timeline notes

Notes are annotations, not analytics data, so the API accepts the read key
for them (same as the dashboard). The agent should log one factual line per
meaningful change — "Deployed new pricing page", "Launched on Product Hunt".
These notes appear on dashboard charts and are cited by the `explain` path,
closing the loop: the agent's own deploy log becomes the evidence for the
next anomaly investigation. Keep notes short (500 chars max) and factual.

## The skill

Install `skills/agentlens-analytics/SKILL.md` into your agent (Claude Code:
`~/.claude/skills/` or project `.claude/skills/`) so it knows the workflow:
discover metrics first, never invent dimension values, ground every claim in
returned numbers.

## Self-observability

With `AGENTLENS_WRITE_KEY` set, every tool call is reported back as an
`mcp_tool_call` event (tool, duration_ms, success). Open the dashboard's
**Agent usage** page to see which tools your agents reach for and where they fail.
