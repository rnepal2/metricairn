# API

Interactive schemas are served at `/docs`; OpenAPI is at `/openapi.json`. All endpoints below use `/api/v1`. Keys select the project; clients cannot override analytical tenant scope.

| Credential | Header | Capability |
|---|---|---|
| Tracking | `X-Write-Key` | Collect events only |
| Read | `X-Read-Key` | Query project data |
| Management | `X-Management-Key` | Configuration, keys, evidence writes, deletion |

`POST /projects` returns all three keys once. If configured, creation requires `X-Provisioning-Token`. `GET /projects/me` resolves the read key’s project. `GET /projects` lists only that project.

| Workflow | Endpoints |
|---|---|
| Collect | `POST /ingest` (`{events: [...]}`), `/ingest/events`; `GET /ingest/ping` |
| Metrics | `GET /query/overview`, `/timeseries`, `/breakdown`, `/dimensions`, `/metrics`, `/realtime`, `/compare`, `/anomalies` |
| Filtered plans | `POST /query/run` |
| Goals | `GET/POST /goals`; `GET /goals/{id}/report`; `DELETE /goals/{id}` |
| Retention | `GET /query/retention` |
| Investigate | `POST /investigations/run`; `GET/POST /investigations`; `GET/PATCH /investigations/{id}` |
| Funnels | `GET/POST /funnels`; `GET /funnels/{id}/report`; `DELETE /funnels/{id}` |
| Context | `GET/POST /projects/{id}/notes` |
| Keys | `GET/POST /keys`; `DELETE /keys/{id}` |
| Transparency | `GET /projects/{id}/data/summary`, `/data/health`; `DELETE /projects/{id}/data` |
| Optional | `/ask`, `/alerts/*`, `/digest/*`, `/query/revenue`, `/query/mcp-usage`, existing `/integrations/*` |

Analytical GET endpoints accept `date_from`/`date_to` where applicable; realtime accepts `minutes` (1–1440). Breakdown accepts dimension, limit (1–100), and `order_by` (visitors/pageviews/events/revenue). Currency-aware legacy reports accept a three-letter currency. See [metric semantics](trust-and-data.md).

## Plans and evidence

`POST /query/run` accepts the [MCP plan format](mcp.md): metric, mode (`total`, `timeseries`, `breakdown`), optional dimension, interval (`day`, `hour`), event name, filters, dates, and limit. Unknown fields are rejected. Missing event names/dimensions fail explicitly. Empty results remain valid; breakdown truncation is disclosed.

`POST /investigations/run` uses the same plan but supports additive counts only. `POST /investigations` requires management and `{title, plan}`; it computes and saves immutable evidence. `PATCH /investigations/{id}` accepts `{status, note}` with status `observed`, `investigating`, `resolved`, or `dismissed`; evidence cannot be patched. Lists return the newest 30 summaries by default, up to 100 via `limit`.

Goals require `{name, event_name}` and management access. Reports require read access. Retention optionally accepts `event_name` for return activity. Project-data deletion removes events, goals, saved evidence, notes, funnels, and delivery configuration/history while preserving the project and keys.

## Collection boundaries

At most 500 events/request, 1 MiB/body, 8 KiB/event properties. Optional `event_id` deduplicates within a project. Timestamps must be valid and not over five minutes ahead. Arbitrary custom data must be minimized by the sender. Read and management endpoints are never authorized by a public tracking key.
