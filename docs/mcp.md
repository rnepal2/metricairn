# MCP Setup

The AgentLens MCP server is **read-only by design** — your agent can query analytics
but never modify them.

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
```

Claude Code: `claude mcp add --transport stdio agentlens -- python -m agentlens_mcp`
Claude Desktop / Cursor: add to MCP config — see `skills/agentlens-analytics/examples/mcp-config.json`.

Hosted mode: `python -m agentlens_mcp --http --port 8001` (streamable HTTP).

## Tools (10, curated)

`list_metrics` · `query_metrics` · `breakdown` · `list_dimension_values` ·
`funnel_report` · `revenue_attribution` · `detect_anomalies` · `ask` ·
`get_realtime` · `mcp_usage`

Full reference: `skills/agentlens-analytics/references/tools.md`.

## The skill

Install `skills/agentlens-analytics/SKILL.md` into your agent (Claude Code:
`~/.claude/skills/` or project `.claude/skills/`) so it knows the workflow:
discover metrics first, never invent dimension values, ground every claim in
returned numbers.

## Self-observability

With `AGENTLENS_WRITE_KEY` set, every tool call is reported back as an
`mcp_tool_call` event (tool, duration_ms, success). Open the dashboard's
**Agent usage** page to see which tools your agents reach for and where they fail.
