# AgentLens MCP — Tool Reference

All tools are **read-only by default**. Every tool accepts `days` (default 30) unless noted. Dates are UTC.

## Discovery

### `list_metrics`
No parameters. Returns the metric catalog (`visitors`, `pageviews`, `sessions`, `events`, `revenue`) and dimension catalog (`path`, `referrer`, `utm_source`, `utm_medium`, `utm_campaign`, `device`, `browser`, `os`, `country`, `event`).

### `list_dimension_values(dimension, days=30)`
Returns the actual values a dimension takes, e.g. real page paths. Call this before filtering on a value you haven't seen.

## Query

### `query_metrics(metric="visitors", days=30, interval="day")`
Time series. `metric` ∈ visitors|pageviews|sessions|events|revenue. `interval` ∈ day|hour.
Response: `[{"t": "<iso>", "value": <number>}, ...]` with zero-filled buckets.

### `breakdown(dimension="path", days=30, limit=10)`
Top values: `[{"value", "visitors", "pageviews", "revenue"}, ...]` sorted by visitors.

### `revenue_attribution(days=30)`
`{total, currency, transactions, revenue_per_visitor, by_source: [{source, revenue}], timeseries}`.

### `funnel_report(funnel, days=30, segment_by="")`
`funnel` matches by name (case-insensitive) or id. Returns per-step `{visitors, conversion_from_start, conversion_from_prev}` plus `overall_conversion`. Steps must be completed in order. With `segment_by` (e.g. `"device"`, `"utm_source"`), also returns per-segment tables — a visitor's segment is the dimension value on their entry-step event.

### `detect_anomalies(days=30)`
Z-score anomalies on daily pageviews and revenue: `[{date, metric, value, expected, z_score, direction}]`, direction ∈ spike|dip.

### `get_realtime()`
Last-30-minutes activity: `{visitors, pageviews, events, top_pages}`.

## Natural language

### `ask(question, days=30)`
Plans the question (LLM when the API has `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, heuristic otherwise) and returns `{answer, data, chart}`. Log of asked questions feeds `mcp_usage`.

## Meta

### `mcp_usage(days=30)`
How agents use this server: `{total_tool_calls, by_tool: [{tool, calls, error_rate, avg_ms}], questions_asked, recent_questions}`.

## Timeline notes

### `list_notes()`
Newest-first timeline annotations (launches, deploys, campaigns). Shown on dashboard charts; cited by anomaly explanations.

### `add_note(text)` — opt-in
Only registered when `AGENTLENS_ENABLE_NOTE_WRITE=1`. Logs one factual line (max 500 chars) to the timeline, e.g. `"Deployed new pricing page"`. Use it when you ship something meaningful — it becomes the evidence future anomaly investigations cite.
