# Metric definitions

All values describe **recorded activity**, not complete business reality. Queries are project-scoped. Windows are UTC `[start, end)`; a date-only `date_to` includes that calendar day. Query windows are limited to 366 days. Internal `ask` and `mcp_tool_call` events are excluded from customer metrics.

| Metric | Definition |
|---|---|
| Visitors | Distinct nonempty visitor IDs in the window |
| Pageviews | Events named `pageview` |
| Sessions | Distinct nonempty session IDs on pageviews |
| Custom events | Occurrences excluding pageviews, revenue, and internal telemetry |
| Event count | Occurrences of one named event |
| Bounce rate | Share of pageview sessions with exactly one pageview |
| Session duration | Last minus first pageview timestamp; an estimate, not engaged time |
| Goal conversion | Visitors with a pageview then the goal event in the window / visitors with a pageview; repeats count once |
| Funnel conversion | Visitors completing configured steps in chronological order / entry visitors; segments use the entry event |

Distinct identities can appear in multiple segments or time buckets. Do not sum bucket uniques into period uniques. Goal conversion is a period measure, not an acquisition cohort; unidentified or pre-entry goal events remain in occurrence counts but do not convert a visitor.

## Retention

Weekly cohorts use a visitor’s first recorded customer event across available project history. Cohort selection follows the query window; return activity can optionally be restricted to an event. Weeks begin Monday UTC. Only completed weeks are measured; incomplete/future cells are `null`, not zero. Week 0 includes acquisition activity. The first selected week may be partial. Missing historical events and cleared browser IDs change the interpretation; there is no cross-device stitching.

## Investigations

The preceding comparison window has equal duration. Pageview/custom-event counts partition by event-stamped source, device, browser, and path. Each dimension reconciles independently to total change, including an explicit remaining tail. Missing tags are visible. Changes are descriptive: weekday mix, seasonality, collection outages, and deployment changes can explain them. Timeline notes provide context, not causal proof. Anomaly scores are screening heuristics, not significance tests.

Reports include resolved plans, metric version, generation time, and evidence ID. Saving re-runs the fixed window and freezes that result; late-arriving events can make it differ from an earlier live preview. Reviews do not rewrite saved evidence. JSON/CSV exports contain project data; treat them accordingly.

## Collection and optional features

The tracker stores random browser-local visitor/session IDs, uses a 30-minute session timeout, preserves landing UTMs, strips arbitrary query strings/fragments, and respects DNT/GPC/disable controls. No cookies are set. Arbitrary custom properties and identities are not automatically anonymized. Server collection is not subject to browser privacy controls. Consent and retention decisions belong to the operator.

Existing revenue reports show positive gross recorded amounts by currency; no FX conversion, net revenue, refunds, MRR, or financial assurance. Source attribution uses recorded session tags; unlinked server events are unattributed. Payment expansion is deferred. Optional model confidence describes a query-path heuristic, not answer accuracy. Model/SQL caveats: [SQL guide](agentic-analytics.md).
