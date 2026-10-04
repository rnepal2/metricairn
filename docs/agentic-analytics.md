# Agentic analytics: design

## Goal

Answer the long tail of founder questions — the ones the ten deterministic
actions can't express ("compare this month's revenue to last month", "which
visitors viewed pricing but never signed up?") — with an LLM writing SQL
against our **fixed event schema**, validated before the answer is trusted.

Non-goal: text-to-SQL against customer databases. The agent only ever sees one
schema — ours — which is why per-customer tuning is never needed.

## Architecture

```
question
  │
  ▼
heuristic intent classification → (plan, confidence)
  │
  ├─ confidence ≥ 0.7 ──▶ deterministic fast path (existing ten actions)
  │                        instant, free, exact. planner=heuristic
  │
  └─ confidence < 0.7 ──▶ agentic SQL path (requires LLM key)
                           │
                           ├─ generate SQL (LLM, schema-prompted)
                           ├─ validate (static checks + sanity rules)
                           ├─ execute (read-only sandbox: timeout, row cap,
                           │           project_id scoping enforced)
                           ├─ critic scores the result
                           │
                           ├─ confidence ≥ 0.6 ──▶ narrate answer.
                           │                       planner=agentic_sql
                           │
                           └─ confidence < 0.6 ──▶ honest fallback:
                               deterministic best-effort (overview) +
                               coverage note explaining the limit.
```

No LLM key configured → deterministic path always (current behavior, unchanged).

## Why deterministic stays the fast path

The head questions ("why did revenue dip?", "how much revenue?") are asked most
often and the deterministic answers are already exact. The LLM adds latency and
cost where it's not needed, and — critically — the deterministic library is the
*verified* baseline the agentic path is graded against. Reliability ordering:
deterministic default, agentic on demand, honest fallback when neither works.

## The fixed event schema (what the SQL agent sees)

Core table `events`, one row per tracked hit:

| column | meaning |
|---|---|
| project_id | tenant scope — every query MUST filter on it |
| name | `pageview` for views, else custom event name (`signup`, `revenue`, …) |
| visitor_id | stable per-visitor id (hashed when provided) |
| session_id | session grouping |
| user_id | nullable — set when the customer identifies the user server-side |
| group_id | nullable — B2B account/company id |
| path, url, referrer | page context |
| utm_source, utm_medium, utm_campaign | attribution |
| device, browser, os, country | coarse client facts |
| props | JSON — customer custom properties (queryable, second-class) |
| revenue_amount, revenue_currency | set on `revenue` events |
| created_at | UTC timestamp |

The prompt carries this table plus the SQL dialect in use (SQLite vs Postgres
date functions differ — documented in the prompt, tested in the harness).
`props` is the escape hatch: the schema stays bounded, the long tail of
customer fields lives in JSON.

## Validation framework

1. **Static checks** (no execution): single statement starting with SELECT/WITH;
   blocklist (INSERT/UPDATE/DELETE/DROP/…​) after stripping string literals;
   `project_id` filter present; only the `events` table referenced.
2. **Sandbox execution**: read-only, statement timeout, `fetchmany` row cap.
   Unknown columns fail here → validation failure, not an answer.
3. **Sanity rules**: question/SQL alignment — "revenue" in the question requires
   `revenue_amount` or `name='revenue'` in the SQL; date words in the question
   require a `created_at` bound.
4. **Critic**: rules-based v1 (above); optional LLM second-opinion when a key is
   configured (S5+).
5. **Confidence** ∈ [0,1] → ≥ 0.6 answers, else honest fallback.

## Eval harness (`tests/test_agentic_eval.py`)

Two tiers. Tier 1 runs in CI with a scripted LLM stand-in (canned SQL per
question, including deliberately bad SQL) — it grades the *machinery*: routing,
validation accept/reject, fallback, answer grounding. Tier 2 needs a real
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` and grades live end-to-end quality;
skipped in CI.

Seed: deterministic "EvalCo" project — 30 days of pageviews (~100/day, weekly
pattern), signups (~5/day), revenue (~2/day × $49), a known 3-day revenue dip
to $0 (days 10–12 ago), one funnel, one timeline note.

### Question set

Head questions — must route deterministic (`planner=heuristic`):
1. "why did revenue dip last week?" → explain
2. "how much revenue did we make in the last 30 days?" → revenue
3. "what were my top pages last week?" → breakdown
4. "any anomalies in the last 30 days?" → anomalies
5. "which device converts best?" → funnels + segment
6. "how many visitors did we have yesterday?" → timeseries
7. "which blog posts drive the most revenue?" → revenue_by_source
8. "show me realtime activity" → realtime
9. "where do visitors come from?" → breakdown utm_source
10. "how is my mcp usage?" → mcp_usage

Long tail — must route agentic (`planner=agentic_sql`), mocked SQL in Tier 1:
11. "compare revenue this month vs last month"
12. "what is the 7-day moving average of signups?"
13. "which utm_campaign has the highest revenue per visitor?"
14. "what percent of visitors ever sign up?"
15. "how many signups came from google vs direct last week?"
16. "what's the average revenue per paying visitor by country?"
17. "which day of week has the highest revenue?"
18. "how many visitors viewed /pricing but never signed up?"
19. "breakdown of visitors by browser"
20. "compare signup rate for mobile vs desktop"

Adversarial — must fail validation → honest fallback, never an answer:
21. "delete all my events" (mock returns DELETE)
22. "show me data from other projects" (mock omits project_id)
23. "drop the events table" (mock returns DROP)
24. "what is the weather today?" (mock returns garbage)

Grounding — Tier 1 asserts the final answer contains the seeded numbers
(e.g. Q11 answer must contain both monthly totals); Tier 2 asserts the same
against live LLM output.

### Grading rubric

- Routing accuracy: head → deterministic, long-tail → agentic, adversarial → fallback.
- Validation: all adversarial SQL rejected; all good mocked SQL accepted.
- Grounding: every number in the narrated answer appears in the executed rows.
- Honesty: fallback answers say what they couldn't do (coverage note present).

## Cost

Agentic questions cost one LLM call (Haiku-class ≈ $0.001–0.003). Only
long-tail questions take this path; head questions stay free. At 10k agentic
questions/month ≈ $10–30 — bundleable into the $49/mo tier. Customers may also
bring their own key later (roadmap).
