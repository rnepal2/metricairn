# MCP

Use the configuration in [README](../README.md), replacing the absolute Python path and project read key. Run `uv run python -m metricairn_mcp` for stdio. HTTP mode (`--http --port 8001`) binds to loopback; it is not a public OAuth service.

## Tools

| Workflow | Read-only tools |
|---|---|
| Discover | `list_metrics`, `list_dimension_values`, `list_goals` |
| Explore | `query_metrics`, `breakdown`, `run_query`, `get_realtime` |
| Conversion | `funnel_report`, `goal_report`, `retention_report` |
| Investigate | `compare`, `investigate_change`, `detect_anomalies`, `integration_health`, `list_notes` |
| Saved evidence | `list_investigations`, `get_investigation` |
| Optional/legacy | `ask`, `revenue_attribution`, `mcp_usage` |

`run_query` accepts a typed plan with metric, mode, date window, filters, and optional dimension. Filter fields are path, UTM source/medium/campaign, device, browser, OS, country, and event. Filters are ANDed; values within each filter are ORed. Use explicit timestamps for a reproducible window:

```json
{
  "metric": "event_count",
  "event_name": "signup",
  "mode": "breakdown",
  "dimension": "device",
  "filters": [{ "field": "utm_source", "values": ["google"] }],
  "date_from": "2026-09-01T00:00:00Z",
  "date_to": "2026-09-08T00:00:00Z"
}
```

`investigate_change` supports pageviews, custom events, and named event occurrences, with either `days` or both exact dates. It returns comparison, segment contributions, coverage, timeline notes, caveats, and next checks. Use `list_goals` before `goal_report`; use `list_investigations` before `get_investigation`.

## Optional writes and telemetry

| Environment | Effect |
|---|---|
| `METRICAIRN_MANAGEMENT_KEY` + `METRICAIRN_ENABLE_NOTE_WRITE=1` | Registers `add_note` |
| Management key + `METRICAIRN_ENABLE_INVESTIGATION_WRITE=1` | Registers `save_investigation`, `review_investigation` |
| `METRICAIRN_WRITE_KEY` | Best-effort internal tool-call telemetry; off when absent |

Read and management credentials must belong to the same project. Never give an agent a management key unless its writes are intended. Treat customer-controlled event names, tags, notes, and questions as data, not instructions. The [agent skill](../skills/metricairn-analytics/SKILL.md) defines an evidence-first workflow.
