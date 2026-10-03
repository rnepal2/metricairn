# Architecture

```
                    ┌──────────────┐
  visitor browser   │  tracker.js  │  <4KB, cookieless, SPA-aware
  ─────────────────▶│  (IIFE)      │──┐ pageview / event / revenue
                    └──────────────┘  │   batched, keepalive
                                      ▼
  your servers ───────────────────▶ POST /api/v1/ingest   (server-side tracking:
                                      │                    ad-blocker-proof)
                    ┌──────────────┐  │
                    │  FastAPI     │◀─┘
                    │  apps/api    │
                    └──────┬───────┘
                           │ SQLAlchemy (SQLite default, Postgres via DATABASE_URL)
                           ▼
                    ┌──────────────┐
                    │  events      │  one row per hit: visitor/session ids,
                    │  projects    │  page, referrer, UTMs, device, props,
                    │  api_keys    │  revenue_amount, created_at
                    │  funnels     │
                    │  notes       │
                    └──────────────┘
                           ▲
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────▼─────┐     ┌──────▼──────┐    ┌──────▼──────┐
  │ Dashboard │     │ MCP server  │    │  Ask API    │
  │ React+TS  │     │ (read-only) │    │  NL → plan  │
  │ shadcn    │     │ 10 tools    │    │  → execute  │
  └───────────┘     └─────────────┘    └─────────────┘
```

## Design decisions

**Events table, not wide columns.** One row per hit with first-class columns for the
dimensions agents actually filter on (path, referrer, UTMs, device, browser, OS,
country) and a JSON `props` bag for everything else. Revenue is an event with
`revenue_amount` — the DataFast-inspired wedge: revenue is a first-class metric,
not an afterthought.

**Python-side aggregation (v1).** The query engine aggregates indexed rows in Python
instead of hand-tuned SQL so it runs identically on SQLite and Postgres. Deliberate
trade: correct and portable now, fast later. At production scale this moves to
hourly/daily materialized rollups (`rollup_hourly`, `rollup_daily` tables) with the
same service interface — see Roadmap.

**Read-only MCP by default.** Research (Oct 2026) shows read-only is the safer default
for agents against production data (Scout, New Relic). AgentLens never got a write
path: PostHog's 1,000+ read-write tools needed a "CLI mode" to stop context flooding.
We ship 10 curated tools.

**Two directions of "agent-native".**
1. Agents query *your* product analytics (`ask`, `query_metrics`, `detect_anomalies`…).
2. The product observes *its own* agent usage: every MCP tool call and every `ask`
   is logged as an event, powering `/query/mcp-usage` and the dashboard's
   "Agent usage" page. Analytics for your agents, by your agents.

**Natural language without lock-in.** `/api/v1/ask` plans via LLM when
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` is set, otherwise a heuristic parser handles the
common questions. Same endpoint serves the dashboard and the MCP `ask` tool, so both
surfaces stay in sync. Responses include `planner: heuristic|llm` for transparency.

**Privacy model.** No cookies; visitor identity is a random ID in `localStorage`
(the user can clear it); no IP storage, no fingerprinting. Server-side tracking is
supported through the same ingest endpoint for ad-blocker-proof collection.

## What's intentionally missing in v1

Multi-user auth (project API keys only), team roles, billing, hosted MCP, session
replay, heatmaps, CAPI forwarding to ad platforms, company identification. See
`docs/roadmap.md` for the ordered list with revenue rationale.
