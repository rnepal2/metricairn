# Contributing

Start with an issue describing the user problem and expected result. Small, focused pull requests are easiest to review. Priorities: instrumentation examples, analytical correctness, reproducible investigations, accessibility, and simpler installation.

## Develop

Use Python 3.12, Node.js 22, uv, and Make. Run commands from the repository root.

```bash
make setup                # locked dependencies
make build                # dashboard + tracker
make api                  # http://localhost:8000, built dashboard included
make web                  # optional Vite development server, :5173
```

Copy `.env.example` to `.env` only if configuration is needed. Core analytics needs no AI key. For fictional demo data, run `uv run python scripts/seed_billwise.py` with the API running against the same database, then select “Explore the simulated Billwise demo.” Seeding replaces this demo project only.

## Verify

```bash
make check
npx playwright install chromium
npm run test:e2e
```

Tests cover tenant and credential isolation, SQL enforcement, metric arithmetic, ingestion, tracker behavior, real MCP stdio discovery, and desktop/mobile journeys. PostgreSQL tests require `TEST_POSTGRES_URL`; live-model evaluation requires provider configuration and can incur costs. CI also builds and boots the container.

`make check` also verifies that workspace versions, lockfiles, and installed packages agree. Before a release, update versions and the changelog, run the checks, and verify CI against the final commit. Published tags stay fixed; new code gets a new version.

`npm run format` applies the project’s Python/TypeScript formatting. Keep metric definitions, API/MCP schemas, tests, and UI labels consistent. Customer activity and internal telemetry must stay separate. Configuration writes require management access. Generated SQL always uses the enforced sandbox. Add regressions for meaningful behavioral changes; update lockfiles for dependency changes.

Never commit credentials, databases, real customer events, generated builds, or test output. Documentation screenshots must use simulated data. Schema startup supports additive changes only; breaking changes need a migration and recovery plan. See [security](SECURITY.md) before reporting a vulnerability.
