# AgentLens — analytics your AI agent can actually query

Privacy-friendly product analytics for founders, with a **read-only MCP server**,
**natural-language querying**, and **revenue attribution** as a first-class metric.

The insight: every analytics tool assumes a *human* reads dashboards. In 2026 the
reader is increasingly an *agent* — Claude Code, Cursor, ChatGPT — and none of the
lightweight tools (Plausible, Fathom, Simple Analytics) were built for that. The
heavyweights (PostHog's 1,000+ MCP tools) flood agent context. AgentLens ships **10
curated tools**, a `SKILL.md` your agent installs, and an ask endpoint that answers
"why did revenue dip last Tuesday?" with real numbers.

And it goes both directions: AgentLens **observes its own agent usage** — every MCP
tool call and every asked question is logged as an event, so the dashboard shows
you how your agents actually use your data.

## 5-minute demo

```bash
# 1. API (SQLite, zero setup)
cd apps/api && .venv/bin/uvicorn app.main:app --port 8000 &
#    or:  docker compose up -d   (Postgres + API)

# 2. Seed 30 days of realistic demo data (includes a launch spike + an outage dip)
python scripts/seed_demo.py
#    → prints your write key (alw_…) and read key (alr_…)

# 3. Dashboard
cd apps/web && npm install && npm run dev
#    → http://localhost:5173 — paste the read key

# (Optional) rebuild the tracker snippet served at /static/agentlens.js:
cd packages/tracker && npm install && npm run build

# 4. Ask your agent (optional)
cd apps/mcp-server && pip install -e .
export AGENTLENS_API_URL=http://localhost:8000 AGENTLENS_READ_KEY=alr_…
python -m agentlens_mcp   # stdio; add to Claude Code / Cursor / Claude Desktop
#    → "any anomalies in the last 30 days?"
```

Try in the dashboard's **Ask AI** page: *"Where is revenue coming from?"*,
*"What were my top pages last week?"*, *"Any anomalies?"*,
*"Why did revenue dip recently?"* (the last one explains the anomaly — segment,
demand check, and timeline notes).

## Live customer demo: Billwise

The fastest way to feel the product: a guided, realistic customer story.

```bash
# Seed the Billwise demo (fictional $10k MRR invoicing SaaS, 60 days of data)
python scripts/seed_billwise.py
# → prints a deterministic demo read key

# Open http://localhost:5173 → "explore the Billwise live demo →"
```

No login needed. The demo page walks through three moments from solo founder
"Maya Chen", each with a real agent Q&A transcript and live charts:

1. **The Monday alert** — *"Why did revenue dip recently?"* → "$0 for 4 days vs
   ~$1,473 expected; traffic held, so this looks like a checkout failure, not
   demand" — citing her deploy note. A ~$9,800/mo leak found in 90 seconds.
2. **Content ROI** — *"Which content actually drives trials?"* → one 3-year-old
   template post beats her Product Hunt launch on attributed revenue. (The
   tracker persists landing UTMs for the whole session, so clean checkout URLs
   still credit the content.)
3. **The funnel leak** — *"Where does checkout leak the most?"* → per-step
   conversion with the biggest leak named.

The dataset is simulated (`scripts/seed_billwise.py`); every number on the demo
page is computed live from it.

## What's inside

| App | Stack | What it does |
|---|---|---|
| `apps/api` | Python, FastAPI, SQLAlchemy | Event ingest, query engine (overview, timeseries, breakdowns, funnels, revenue attribution, robust anomalies), NL ask endpoint, project API keys |
| `apps/web` | React, TypeScript, Vite, shadcn-style, Recharts | Dashboard: Overview, Realtime, Events, Revenue, Funnels, Ask AI, Alerts, Agent usage, Settings, Billwise demo |
| `apps/mcp-server` | Python, `mcp` | 10 curated read-only tools (stdio + streamable HTTP), self-usage reporting |
| `packages/tracker` | TypeScript → IIFE | <4KB cookieless snippet, SPA-aware, session UTM persistence, `agentlens.event()` / `agentlens.revenue()` |
| `skills/agentlens-analytics` | SKILL.md | Installable agent skill: workflow, tool reference, examples |

Key API routes: `POST /api/v1/ingest` (write key; browser *or* server-to-server —
ad-blocker-proof), `GET /api/v1/query/*` (read key), `POST /api/v1/funnels`,
`POST /api/v1/ask`. Full reference: `docs/api.md`. Interactive docs at `/docs`.

## Why this wins (research-backed)

- **Revenue-first, like DataFast's $30k MRR wedge** — lightweight privacy tools don't
  tie visits to revenue; AgentLens does it natively (`revenue_per_visitor`,
  revenue by source).
- **10 tools, not 1,000** — PostHog's MCP server needed a special "CLI mode" to
  stop flooding agent context. Curation is the feature.
- **Read-only by default** — the safer pattern (Scout, New Relic); agents query
  production data without write risk.
- **SKILL.md distribution** — progressive-disclosure skill so agents discover the
  workflow; the 2026 GTM for dev tools.
- **Transparent by design** — ask responses say whether a heuristic or an LLM
  planned them; pricing and methodology are public (the anti-pattern: hidden
  pricing + zero reviews across the category).

## Repo map

```
apps/api          FastAPI backend + pytest suite
apps/web          React dashboard
apps/mcp-server   MCP server
packages/tracker  JS snippet (tsup build → dist/agentlens.js)
skills/           Installable SKILL.md (+ references, examples)
docs/             architecture.md, api.md, mcp.md, roadmap.md
scripts/          seed_demo.py
infra/            (docker-compose.yml at repo root)
```

## Tests

```bash
cd apps/api && .venv/bin/pytest -q        # 8 tests: ingest, metrics math, funnels, anomalies, NL plans, endpoints
```

## License

Private — all rights reserved (for now).
