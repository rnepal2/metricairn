# Verification

Checks against the current source are recorded here; these do not indicate a new release. CI is the authority for Linux/container/PostgreSQL results.

| Local check | Result, 2026-10-05 |
|---|---|
| Locked dependency setup, version consistency, Ruff, TypeScript, production builds | Passed |
| Python regression suite | 223 passed; 3 opt-in/service-dependent skips (two PostgreSQL tests, one live-provider test) |
| SDK contracts | 40 passed with mocked HTTP; native OpenAI/Anthropic/Google and compatible Responses/Chat Completions |
| Live Muse MCP/API/SQL evaluation | Six synthetic cases passed with `muse-spark-1.3-contributor`, Responses, minimal reasoning, 20-second timeout; observed 1.72–7.13 seconds/case |
| Tracker contract tests | 9 passed |
| MCP stdio initialization/discovery | Passed; typed plans and annotations for question history and optional telemetry |
| Fresh Python-only connector installation | Passed; `uv sync --locked --no-dev`, version 0.2.0 handshake, 20-tool discovery, catalog and query calls |
| Browser product journeys | 6 passed; JSON-error recovery, MCP examples, goals, evidence save/review/export, retention, navigation, restoration, and mobile layout |
| Billwise replay after naming cleanup | Passed; actual stdio MCP calls against the running API and preserved local demo data |

Muse's default/low reasoning exceeded the shorter request budgets; the passing run used the settings above. This small corpus does not establish general model accuracy or production latency. PostgreSQL and Docker run in CI; real payment/delivery integrations and production load/recovery were not validated.

Current tracker is approximately 3.7 KB minified. The dashboard entry is approximately 275 KB / 89 KB gzip, with charts loaded separately (390 KB / 113 KB gzip).
