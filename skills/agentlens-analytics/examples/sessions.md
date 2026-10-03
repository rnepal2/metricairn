# Example agent sessions

## "Why did revenue dip last Tuesday?"

1. `detect_anomalies(days=30)` → confirms a revenue dip on 2026-09-22 (z = -3.1).
2. `breakdown(dimension="utm_source", days=14)` → Google's share dropped the same week.
3. `query_metrics(metric="visitors", days=14)` → visitors steady — conversion, not traffic, fell.
4. Answer: "Revenue dipped 38% on Sep 22 vs the daily average. Traffic was flat, so this was a conversion drop concentrated in Google-sourced visitors. Check the /pricing page changes shipped that day."

## "Which landing page converts best?"

1. `list_dimension_values(dimension="path")` → learn real paths.
2. `funnel_report(funnel="/pricing → signup")` per candidate landing page is not supported in one call — instead compare `breakdown(dimension="path")` visitors against a `signup` event breakdown, or define one funnel per landing page in the dashboard and call `funnel_report` for each.

## "What are agents asking about?"

1. `mcp_usage(days=30)` → top tools, error rates, and the literal recent questions your agents asked. Use it to find which data your team reaches for — and which tools need better descriptions.
