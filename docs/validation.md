# Verification

Release checks and their executed results are recorded here; CI is the authority for Linux/container/PostgreSQL results.

| Local check | Result, 2026-10-04 |
|---|---|
| Locked dependency setup, Ruff, TypeScript, production builds | Passed |
| Python regression suite | 176 passed; 3 service-dependent skips (two PostgreSQL tests, one live-provider test) |
| Tracker contract tests | 9 passed |
| MCP stdio initialization/discovery | Passed; typed plans, default read-only surface |
| Browser product journeys | 2 journeys passed, including goals, evidence save/review/export, retention, navigation, restoration, and mobile layout |

Skipped locally: PostgreSQL, Docker, live-provider generation, real payment/delivery integrations, and production load/recovery. CI separately builds/boots the container and runs disposable PostgreSQL checks. No provider accuracy or production capacity is claimed.

Current tracker is approximately 3.8 KB minified. The dashboard entry is approximately 274 KB / 88 KB gzip, with charts loaded separately (390 KB / 113 KB gzip). One upstream Starlette TestClient deprecation warning remains; tests pass without hiding it.
