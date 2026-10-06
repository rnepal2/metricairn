# Changes

## 0.2.0 — 2026-10-06

- Added native OpenAI, Anthropic, and Google SDK adapters plus configurable Responses/Chat Completions endpoints such as Meta Muse, with explicit provider/model selection and legacy configuration support.
- Added bounded provider timeouts, sanitized failure diagnostics, connection cleanup, SDK contract tests, and an opt-in live MCP/API/SQL evaluation using synthetic data.
- Refined README positioning, setup, scope, and the clearly fictional Billwise example.
- Documented the Python-only MCP connector installation, deployment requirements, question history, and optional provider/telemetry effects.
- Corrected MCP tool annotations to reflect stored questions and configured usage telemetry.
- Added the Billwise walkthrough and real MCP replay script, with exact conversion/retention windows and regression coverage.
- Improved dashboard and MCP errors for non-JSON or malformed API responses.
- Removed compatibility aliases from the previous product name; configuration, tracker URLs, and browser globals now use Metricairn consistently.
- Synchronized workspace and runtime versions, including the MCP handshake, with an automated version consistency check.
- Clean tracker builds remove obsolete assets; browser regression tests disable AI providers to keep verification deterministic.
- Updated CI actions to supported runtimes and pinned their commits and Linux runner image.

**Upgrade:** use `METRICAIRN_*` MCP settings, `/static/metricairn.js`, and `window.metricairn`. Re-enter keys if browser credentials were stored under an older name. The default SQLite file is `data/metricairn.db`; preserve an explicit `DATABASE_URL` for existing data. Project keys and tracker identifiers remain valid. See [operations](docs/operations.md#existing-installations).

## 0.1.0 — open-source release

- Initial Metricairn release; MIT license, one-container installation, concise guides and contribution templates.
- Typed filtered queries, custom-event goals, first-observed weekly retention, and change investigations with collection checks and exportable evidence.
- Immutable saved reports and separate review decisions; 20 MCP tools and three opt-in management tools.
- Scoped ingestion/read/management credentials, rotation, enforced SQL tenant/time boundaries, cancellation, bounded payloads and event deduplication.
- Tracker privacy/retry/navigation controls, API-computed simulated demo, responsive/error-aware UI, locked tooling and SQLite/PostgreSQL/container/browser checks.

**Migration:** administrative actions require a private management key. The original tracking/read credentials remain valid. Preserve the database URL; see [operations](docs/operations.md). Existing optional revenue functionality is retained; payment and billing expansion is deferred.
