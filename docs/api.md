# API Reference (v1)

Base URL: `http://localhost:8000`. Interactive docs: `GET /docs` (Swagger).

Auth: `X-Write-Key: alw_…` for ingest, `X-Read-Key: alr_…` for everything else.
Keys are project-scoped — you can only ever see your own project's data.

## Projects

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/projects` | — | Create project; returns `write_key` + `read_key` (shown once) |
| GET | `/api/v1/projects` | — | List projects (id/name/domain only) |
| GET | `/api/v1/projects/me` | read | Project for this read key (dashboard login) |
| POST | `/api/v1/projects/{id}/notes` | read | Timeline annotation |
| GET | `/api/v1/projects/{id}/notes` | read | List annotations |

## Ingest

`POST /api/v1/ingest` (write key). Body: `{"events": [...]}` (max 500/batch).
Event: `{name, url, referrer, session_id, visitor_id, device, browser, os, country,
props{}, revenue_amount, revenue_currency, at?}`. `name: "pageview"` for page views;
`"revenue"` with `revenue_amount` for purchases. UTM params are parsed from `url`
query strings; the JS tracker persists landing UTMs for the whole session, so
conversions attribute back to the campaign even when the checkout URL is clean.
server-side. Works browser-to-server *and* server-to-server (ad-blocker-proof).

## Query (read key)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/query/overview` | visitors, pageviews, sessions, bounce_rate, avg_session_seconds, events, revenue |
| GET | `/api/v1/query/timeseries?metric=&interval=` | zero-filled series; metric ∈ visitors\|pageviews\|sessions\|events\|revenue; interval ∈ day\|hour |
| GET | `/api/v1/query/breakdown?dimension=&limit=` | top values with visitors/pageviews/revenue; dimension ∈ path\|referrer\|utm_source\|utm_medium\|utm_campaign\|device\|browser\|os\|country\|event |
| GET | `/api/v1/query/dimensions?dimension=` | distinct values a dimension actually takes (for agents) |
| GET | `/api/v1/query/metrics` | metric/dimension catalog (agent entry point) |
| GET | `/api/v1/query/realtime` | last-30-min activity |
| GET | `/api/v1/query/revenue` | total, transactions, revenue_per_visitor, by_source, timeseries |
| GET | `/api/v1/query/anomalies` | robust anomalies on daily pageviews + revenue (same-weekday median/MAD baseline, sustained multi-day runs, partial current day excluded from dip detection) |
| GET | `/api/v1/query/mcp-usage` | agent tool-call counts, error rates, recent questions |

All range queries accept `date_from` / `date_to` (ISO 8601, default last 30 days).

## Funnels

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/funnels` | read | `{name, steps: [{kind: page\|event, value}]}` |
| GET | `/api/v1/funnels` | read | List |
| GET | `/api/v1/funnels/{id}/report` | read | Ordered conversion: per-step visitors, from-start and from-previous rates |

## Ask (natural language)

`POST /api/v1/ask` (read key): `{"question": "..."}` → `{answer, data, chart?, planner}`.
`chart` is `{type: timeseries|bar, x_key, y_key, title}` when a visualization fits.
`planner` is `heuristic` or `llm`. Every question is logged as an `ask` event.
