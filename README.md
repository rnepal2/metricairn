# Metricairn

**Free, self-hosted product analytics for your dashboard and AI agent.**

See what changed, where the change is concentrated, and what to check next. Every investigation exposes its query plan, comparison windows, collection coverage, and caveats. Save the evidence; record your decision separately.

![Metricairn investigation with simulated data](docs/assets/investigation.png)

## Start

```bash
git clone https://github.com/rnepal2/metricairn.git
cd metricairn
docker compose up --build
```

Open **http://localhost:8000**, create a project, and save the three keys shown once. The container serves the dashboard, API, and tracker; SQLite data persists in a named volume. No account, cloud service, or AI key required. For source development, see [CONTRIBUTING](CONTRIBUTING.md).

Install the tracker on your site:

```html
<script defer src="https://YOUR-HOST/static/metricairn.js"
  data-api="https://YOUR-HOST/api/v1/ingest" data-key="alw_YOUR_TRACKING_KEY"></script>
```

Track a meaningful action with `window.metricairn.event('signup')`, then define it as a goal in the dashboard. HTTPS and a reachable deployment are required for a real site; the local container binds to loopback. See [deployment](docs/operations.md).

## What you get

- Traffic, realtime activity, custom events, ordered funnels, conversion goals, and weekly retention.
- Filtered analytics queries and change investigations with additive segment counts, coverage checks, timeline context, and evidence export.
- Immutable saved reports with separate review status and notes.
- **20 read-only MCP tools**, plus three optional management tools. Deterministic workflows run without an LLM; natural-language SQL is optional.
- A small browser tracker with SPA navigation, bounded retries, deduplication, query cleanup, and DNT/GPC controls.
- Scoped keys, rotation, project-data deletion, optional alerts and digests. Existing recorded-revenue support remains optional; payment and billing expansion is deferred.

## Connect an agent

After `make setup`, configure your MCP client:

```json
{
  "mcpServers": {
    "metricairn": {
      "command": "/ABSOLUTE/REPO/.venv/bin/python",
      "args": ["-m", "metricairn_mcp"],
      "env": {
        "METRICAIRN_API_URL": "http://localhost:8000",
        "METRICAIRN_READ_KEY": "alr_YOUR_READ_KEY"
      }
    }
  }
}
```

Try: **“Investigate signup changes over the last week. Check collection coverage and show the largest changed segments before suggesting a cause.”** [MCP reference](docs/mcp.md).

## Scope

Metricairn is an early open-source release for small teams operating their own analytics. Its focus is an inspectable investigation workflow—not feature parity with PostHog. There are no hosted user accounts, OAuth grants, session replay, feature flags, experiments, or high-volume rollups. Cookieless tracking still uses browser-local identifiers. [Metric definitions](docs/trust-and-data.md) · [Security](SECURITY.md).

[API](docs/api.md) · [Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md) · [Product direction](docs/strategy.md)

[MIT licensed](LICENSE). All implemented features are free; there is no paid tier or license server. Self-hosting and optional external providers have their own costs. Contributions are welcome through issues and pull requests.
