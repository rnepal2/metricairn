---
name: agentlens-analytics
description: Query AgentLens product analytics from an AI agent via MCP. Use when the user asks about website traffic, pageviews, visitors, revenue attribution, funnels, anomalies, or wants data-driven answers like "why did revenue dip last Tuesday" grounded in their own product data.
---

# AgentLens Analytics

AgentLens is privacy-friendly product analytics with a read-only MCP server. Query live data instead of guessing.

## Setup

The MCP server needs two environment variables:

```bash
AGENTLENS_API_URL=http://localhost:8000  # or your hosted API
AGENTLENS_READ_KEY=alr_...               # read key from POST /api/v1/projects
```

Add to your MCP client config (Claude Code: `claude mcp add`; Claude Desktop / Cursor: config JSON — see `examples/mcp-config.json`). The server is read-only by design: it cannot modify analytics data.

## Workflow

1. **Discover first.** Call `list_metrics` to see available metrics and dimensions before querying. Use `list_dimension_values` to learn the actual page paths, UTM sources, or event names in the data — never invent dimension values.
2. **Query.** Prefer curated tools over raw exploration: `query_metrics` for trends, `breakdown` for top-N, `revenue_attribution` for money questions, `funnel_report` for conversion, `detect_anomalies` for spikes/dips.
3. **Ask in natural language.** The `ask` tool handles questions like "which landing page converts best from Google traffic?" — it plans and executes the query and returns an answer with data.
4. **Ground every claim.** Cite the numbers the tools returned. If a tool returns no data, say so — do not extrapolate.
5. **Respect ranges.** Default to the last 30 days; use the `days` parameter when the user names a window.

## Tool reference

See `references/tools.md` for the full tool catalog with parameters and response shapes.

## Examples

See `examples/` for copy-paste MCP configs and sample agent sessions.

## Troubleshooting

- `AGENTLENS_READ_KEY is not set` → export the env var before starting the server.
- Empty results → the project may have no events yet; check `get_realtime` to confirm tracking works, and verify the snippet is installed (see the dashboard Settings page).
- Slow `ask` → the question is planned by heuristic when no LLM key is configured on the API; set `ANTHROPIC_API_KEY` on the API server for smarter planning.
