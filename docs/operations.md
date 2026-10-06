# Self-hosting

The default Docker Compose deployment binds to `127.0.0.1:8000`, serves UI/API/tracker, and stores SQLite in a named `data` volume. Stop with `docker compose down`; **`down -v` deletes the database**. Keep source deployments running from the repository root so API and scripts resolve the same database.

| Setting | Purpose |
|---|---|
| `DATABASE_URL` | SQLite by default; `postgresql+psycopg://...` for PostgreSQL |
| `PROVISIONING_TOKEN` | Restricts project creation; required before public exposure |
| `CORS_ORIGINS` | Comma-separated trusted dashboard origins |
| `SCHEDULER_ENABLED` | Off by default; enable on exactly one process for alerts/digests |
| Provider/delivery settings | Optional; see `.env.example` |

Compose forwards only provisioning/CORS configuration and disables scheduling. To use PostgreSQL, AI, or delivery providers in a container, explicitly add the corresponding environment variables. Docker Compose does not automatically pass every `.env` field to the container.

For AI, select a provider using [provider setup](agentic-analytics.md#provider-setup). For example, add `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API`, and `LLM_API_KEY` under the API service's `environment` for a compatible endpoint. Pass values from ignored `.env` or a deployment secret store; never commit credentials in Compose or `.env.example`. Restart the API after configuration changes.

For a public installation, use TLS and a reverse proxy with request limits; restrict management access, protect read keys, redact key-bearing logs, and test backup/restore before collecting real data. There are no hosted accounts or OAuth permissions. `/health` tests process health; `/ready` tests database connectivity. For first-party script/collection routing, see [proxy example](first-party-proxy.md).

Back up SQLite with its backup API or after stopping writes; do not copy a live database file blindly. Use `pg_dump` and a restore drill for PostgreSQL. The application does not implement automatic event-retention jobs. Deleting a project’s data also deletes saved reports. Exports and backups need their own retention policy.

## Existing installations

Version 0.2.0 removes compatibility aliases from the previous product name. Existing `alw_`/`alr_`/`alm_` keys and tracker identifiers remain valid.

Before upgrading, back up the database and set `DATABASE_URL` explicitly to the existing file or PostgreSQL database. The default SQLite file is now `data/metricairn.db`; older filenames are not detected automatically. To adopt the default filename, stop all API processes and copy the database using SQLite's backup API before restarting. Keep the original backup until the upgraded installation is verified.

Use `METRICAIRN_*` MCP environment variables, `/static/metricairn.js`, and `window.metricairn`. Update custom snippets and client configuration. If credentials were saved under older browser storage names, re-enter the existing read key and optional management key in the dashboard. No data conversion or key rotation is required for this upgrade.

Older projects without private management access can issue a key locally:

```bash
uv run python scripts/issue_management_key.py PROJECT_ID
```

Back up the database first; the command prints a private key once. Startup supports additive schema repair, not arbitrary schema migrations. PostgreSQL parity tests use a disposable database via `TEST_POSTGRES_URL`; never point them at production.
