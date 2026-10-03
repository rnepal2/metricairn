# Roadmap

Ordered by revenue leverage for a solo developer. v1 is the demo-ready core.

## v1.1 — Conversion essentials
- [ ] Goals (define once: "signup completed" — reused across dashboard, funnels, ask)
- [ ] UTM/campaign comparison view ("spend vs revenue" table)
- [ ] Weekly email digest (top movers + anomalies)
- [ ] CSV export on every table

## v1.2 — Make the agent smarter
- [ ] `compare` MCP tool (period-over-period with significance note)
- [ ] Saved questions: pin ask results to the dashboard
- [ ] Anomaly explanations ("revenue dipped because Google traffic fell 40%") — correlate breakdowns automatically
- [ ] Slack webhook on anomalies

## v1.3 — Scale the engine
- [ ] Hourly/daily materialized rollups (same service interface; SQLite→Postgres path already abstracted)
- [ ] Server-side CAPI forwarding (Meta/Google Ads) — ad-blocker-proof attribution loop
- [ ] Bot-score filtering v2

## v2 — Team & money
- [ ] Multi-user auth, roles, per-seat pricing
- [ ] Hosted MCP (OAuth) — one-click connect, no local server
- [ ] Usage-based billing: events metered, generous free tier (the DataFast/Web3Forms playbook)
- [ ] Company identification for B2B (the ObserviX gap: "which companies visited")

## Explicit non-goals
Session replay and heatmaps (Matomo owns it; heavy infra), A/B testing engine,
being a CDP. Stay the lightweight, revenue-first, agent-native wedge.
