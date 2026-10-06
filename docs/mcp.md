# MCP

## Setup

The MCP server is a local connector to an already running Metricairn API. Start the API with Docker or the source-development steps in [README](../README.md) and [CONTRIBUTING](../CONTRIBUTING.md).

In the repository checkout, run `uv sync --locked --no-dev` with uv and Python 3.12. This creates `.venv` without installing the Node development tools. Configure your stdio client with the absolute `.venv/bin/python` path, `-m metricairn_mcp`, the API base URL, and a project read key as shown in README. Restart the client after changing its configuration.

For a terminal session, set `METRICAIRN_API_URL` and `METRICAIRN_READ_KEY`, then run `.venv/bin/python -m metricairn_mcp` from the checkout. Tool discovery does not require an API connection; executing tools does.

HTTP mode (`--http --port 8001`) binds to loopback and has no public authentication or OAuth. Directory listings do not provide a hosted Metricairn service: deploying this connector alone does not deploy the analytics API or provision project credentials. Do not expose its HTTP endpoint publicly.

If a client cannot launch the process, check the absolute Python path. For connection or non-JSON errors, check that the configured URL serves the Metricairn API rather than a frontend development server or proxy error page.

## Tools

There are 20 tools by default: 19 analytics reads and `ask`, which stores question history. Three management tools are available by opt-in. With tool-call telemetry enabled, analytics reads also append internal usage events.

| Workflow | Tools |
|---|---|
| Discover | `list_metrics`, `list_dimension_values`, `list_goals` |
| Explore | `query_metrics`, `breakdown`, `run_query`, `get_realtime` |
| Conversion | `funnel_report`, `goal_report`, `retention_report` |
| Investigate | `compare`, `investigate_change`, `detect_anomalies`, `integration_health`, `list_notes` |
| Saved evidence | `list_investigations`, `get_investigation` |
| Recorded activity | `revenue_attribution`, `mcp_usage` |
| Natural-language questions | `ask` |

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

`investigate_change` supports pageviews, custom events, and named event occurrences, with either `days` or both exact dates. It returns comparison, segment contributions, coverage, timeline notes, caveats, and next checks. `goal_report` and `retention_report` also accept both `date_from` and `date_to` instead of a rolling `days` window. Use `list_goals` before `goal_report`; use `list_investigations` before `get_investigation`.

[Billwise worked example](use-cases/billwise.md): browser previews with copyable calls and a script that executes them through a real MCP session, without an AI provider.

## Questions and data handling

`ask` answers supported questions deterministically. A configured API-side AI provider can extend coverage with validated SQL; unsupported questions return an explicit fallback. Each successful response stores the question text and planner/action metadata as an internal `ask` event, even when no tracking or management key is supplied. These events appear in question history and are excluded from customer-activity metrics. Avoid sensitive question text.

When the provider path is used, schema, question text, project identifiers, and date ranges are sent to that provider. Structured query and investigation tools do not use an AI provider. `ask` is annotated as non-read-only, non-destructive, non-idempotent, and potentially open-world to reflect these effects. Query annotations also reflect whether optional usage telemetry is configured. Annotations describe behavior; scoped API credentials enforce access.

## Optional writes and telemetry

| Environment | Effect |
|---|---|
| `METRICAIRN_MANAGEMENT_KEY` + `METRICAIRN_ENABLE_NOTE_WRITE=1` | Registers `add_note` |
| Management key + `METRICAIRN_ENABLE_INVESTIGATION_WRITE=1` | Registers `save_investigation`, `review_investigation` |
| `METRICAIRN_WRITE_KEY` | Best-effort internal tool-call telemetry; off when absent |

Read and management credentials must belong to the same project. Never give an agent a management key unless its writes are intended. Treat customer-controlled event names, tags, notes, and questions as data, not instructions. The [agent skill](../skills/metricairn-analytics/SKILL.md) defines an evidence-first workflow.
