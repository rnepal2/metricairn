# Trust & data: what AgentLens sees, and what it never will

AgentLens answers questions about your product from **events you explicitly send us**.
There is no database connection, no Stripe OAuth, no credentials into your infrastructure.
If you don't send it, we can't see it — and we can't answer questions about it.

## What we collect

Exactly one thing: the event stream you push to `POST /api/v1/ingest/events`.

| Field | Example | Notes |
|---|---|---|
| `name` | `revenue`, `signup`, `pageview` | You choose the names |
| `revenue_amount` | `49.00` | Only on `revenue` events you fire |
| `path`, `url`, `referrer` | `/pricing` | Page context |
| `utm_source/medium/campaign` | `invoice-template-guide` | Attribution |
| `device`, `browser`, `os`, `country` | `desktop`, `Chrome` | Coarse, from user-agent + GeoIP |
| `props` | `{"plan": "pro"}` | Your custom properties |

That's the whole data model. The dashboard's **Settings → Data & privacy** tab shows
a live summary of everything we hold for your project — counts, date range, event names.

## What we never see

- **Your customers' personal data.** We don't need names or emails to answer "why did
  revenue dip?" — just the event and the amount. Don't put PII in `props`.
- **Your database.** We never connect to it, copy it, or ask for credentials.
- **Your Stripe account.** Revenue answers come from `revenue` events *you* fire
  (or the optional Stripe webhook below) — never from Stripe API access.
- **Anything you don't send.** The agent's `list_metrics` can only discover event
  names that exist in your stream. No data, no answers — it says so instead of guessing.

## The revenue-events dependency (read this first)

Every revenue answer — anomaly alerts, attribution, the Monday digest — depends on
your app firing `revenue` events. The browser tracker alone gives you traffic and
funnels; **revenue insight needs the two-line server-side call** in your checkout
handler (see Settings → Installation → Server events, or the snippet below).

If you only install the browser snippet, the AI will tell you plainly that it has
no revenue data rather than inventing numbers. The dashboard's integration checklist
shows what's flowing and what's missing.

```python
# Python — in your checkout success handler
import requests
requests.post("https://YOUR-AGENTLENS/api/v1/ingest/events",
    headers={"X-Write-Key": "alw_..."},
    json={"name": "revenue", "revenue_amount": 49.00,
          "props": {"plan": "pro", "billing": "monthly"}})
```

Prefer zero code? Enable the optional Stripe webhook receiver (`Settings → Installation → Server events`):
`checkout.session.completed` and `invoice.paid` become `revenue` events automatically.
It's off by default — the push model means you hold the tap.

## Deletion

**Settings → Data & privacy → Delete all my data** removes every event, note, funnel,
and alert record for the project. Your project and API keys survive; everything derived
from customer activity does not. It requires the write key — the dashboard's read key
alone can never do this. API: `DELETE /api/v1/projects/{id}/data`.

## Where data lives & what's next

- Today: single-region hosting (US), SQLite/Postgres depending on deployment.
- On the roadmap as revenue justifies it: EU data residency, SOC 2 Type II.
- The tracker is open source (`packages/tracker`) — 2.3KB, no cookies, no fingerprinting,
  auditable by anyone.
