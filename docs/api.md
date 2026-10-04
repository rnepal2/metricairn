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
| GET | `/api/v1/funnels/{id}/report` | read | Ordered conversion: per-step visitors, from-start and from-previous rates. `?segment_by=device` adds per-segment tables (top 8 by entry visitors; a visitor's segment is the dimension value on their entry-step event) |

## Ask (natural language)

`POST /api/v1/ask` (read key): `{"question": "..."}` → `{answer, data, chart?, planner}`.
`chart` is `{type: timeseries|bar, x_key, y_key, title}` when a visualization fits.
`planner` is `heuristic` or `llm`. Every question is logged as an `ask` event.

## Alert delivery

Anomaly detection is only useful if someone sees it. Channels get a message
when a fresh anomaly matches a rule; the in-process scheduler runs the check
every `ALERTS_CHECK_MINUTES` (default 30). With no custom rules, a built-in
default applies: any metric/direction, |z| ≥ 3, 24h cooldown. Cooldowns are
tracked per (channel, anomaly), and every decision is logged.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/alerts/channels` | write | `{kind: email\|slack, target}` — address or `https://hooks.slack.com/…` webhook |
| GET | `/api/v1/alerts/channels` | read | List (webhook URLs masked) |
| DELETE | `/api/v1/alerts/channels/{id}` | write | Remove |
| POST | `/api/v1/alerts/channels/{id}/test` | write | Send a test message |
| POST | `/api/v1/alerts/rules` | write | `{name, metric, direction, min_z, cooldown_hours}` |
| GET | `/api/v1/alerts/rules` | read | List |
| DELETE | `/api/v1/alerts/rules/{id}` | write | Remove |
| GET | `/api/v1/alerts/deliveries` | read | Delivery log: sent / failed / skipped |
| POST | `/api/v1/alerts/check` | write | Run one check cycle now (same as the scheduler) |

Email delivery uses Resend (`RESEND_API_KEY`, from `ALERTS_FROM_EMAIL`).
Without it, email attempts are logged as failed with `skipped: RESEND_API_KEY
not configured` — Slack needs no API key. For multi-worker deployments set
`ALERTS_SCHEDULER_ENABLED=false` on all but one instance.

## Weekly digest

The Monday-morning email for founders who don't live in dashboards: WoW
deltas, this week's anomalies, top content by attributed revenue, and the
funnel headline. Delivered to the project's alert channels (no separate
channel setup). Schedule is UTC (`hour_utc`, default Monday 12:00 ≈ 7–8am US
Eastern); the scheduler sends once per slot and never backfills.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/digest/settings` | read | `{enabled, weekday, hour_utc, last_sent_at}` |
| PUT | `/api/v1/digest/settings` | write | `{enabled, weekday 0–6, hour_utc 0–23}` |
| POST | `/api/v1/digest/preview` | read | Compile without sending |
| POST | `/api/v1/digest/send` | write | Send now (requires enabled) |
