# Tool reference

The maintained catalog, parameters, examples, and opt-in flags are in [docs/mcp.md](../../../docs/mcp.md). MCP `tools/list` exposes the live typed schemas; `list_metrics` exposes the API’s definitions.

Start an investigation with `investigate_change(metric="event_count", event_name="signup", days=7)`. Use `run_query` to verify a segment or fixed window. Inspect coverage and caveats, then optionally save the plan using management-authorized tools. Retention uses first-observed visitor cohorts; goals use period conversion after a pageview.
