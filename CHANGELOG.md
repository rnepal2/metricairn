# Changes

## Unreleased

- Refined README positioning, setup, scope, and the clearly fictional Billwise worked example.
- Documented the Python-only MCP connector installation, deployment requirements, question history, and optional provider/telemetry effects.
- Corrected MCP tool annotations to reflect stored questions and configured usage telemetry.
- Added the Billwise walkthrough and real MCP replay script, with exact conversion/retention windows and regression coverage.
- Improved dashboard and MCP errors for non-JSON or malformed API responses.

## 0.1.0 — open-source release

- Renamed AgentLens to Metricairn; MIT license, one-container installation, concise guides and contribution templates.
- Typed filtered queries, custom-event goals, first-observed weekly retention, and change investigations with collection checks and exportable evidence.
- Immutable saved reports and separate review decisions; 20 MCP tools and three opt-in management tools.
- Scoped ingestion/read/management credentials, rotation, enforced SQL tenant/time boundaries, cancellation, bounded payloads and event deduplication.
- Tracker privacy/retry/navigation controls, API-computed simulated demo, responsive/error-aware UI, locked tooling and SQLite/PostgreSQL/container/browser checks.

**Migration:** administrative actions require a private management key. The original tracking/read credentials remain valid. Legacy browser globals and MCP environment variables are supported during rename migration. Preserve the database URL; see [operations](docs/operations.md). Existing optional revenue functionality is retained; payment and billing expansion is deferred.
