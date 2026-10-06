# Verification

Checks against the current source are recorded here; these do not indicate a new release. CI is the authority for Linux/container/PostgreSQL results.

| Local check | Result, 2026-10-05 |
|---|---|
| Locked dependency setup, Ruff, TypeScript, production builds | Passed |
| Python regression suite | 182 passed; 3 service-dependent skips (two PostgreSQL tests, one live-provider test) |
| Tracker contract tests | 9 passed |
| MCP stdio initialization/discovery | Passed; typed plans and annotations for question history and optional telemetry |
| Fresh Python-only connector installation | Passed; `uv sync --locked --no-dev`, isolated API provisioning, 20-tool discovery, catalog and query calls |
| Browser product journeys | 6 passed; JSON-error recovery, MCP examples, goals, evidence save/review/export, retention, navigation, restoration, and mobile layout |

Skipped locally: PostgreSQL, Docker, live-provider generation, real payment/delivery integrations, and production load/recovery. CI separately builds/boots the container and runs disposable PostgreSQL checks. No provider accuracy or production capacity is claimed.

Current tracker is approximately 3.8 KB minified. The dashboard entry is approximately 275 KB / 89 KB gzip, with charts loaded separately (390 KB / 113 KB gzip). One upstream Starlette TestClient deprecation warning remains; tests pass without hiding it.
