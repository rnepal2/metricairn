# Natural-language analytics

Common questions use a deterministic intent parser and tested aggregate services. The SQL route extends the vocabulary when a provider is configured and `AGENTIC_SQL_ENABLED=true`.

## Provider setup

Set `LLM_PROVIDER`, `LLM_MODEL`, and the selected provider's credential in ignored `.env` or the server environment. Keep `.env.example` credential-free.

| Provider | SDK / API | Credential |
|---|---|---|
| `openai` | OpenAI SDK, Responses | `OPENAI_API_KEY` |
| `anthropic` | Anthropic SDK, Messages | `ANTHROPIC_API_KEY` |
| `google` | Google GenAI SDK, Gemini | `GEMINI_API_KEY` |
| `openai_compatible` | OpenAI SDK, selected protocol | `LLM_API_KEY` + `LLM_BASE_URL` |

For compatible endpoints, set `LLM_API=chat_completions` or `responses` according to the service. Meta Muse example (credential supplied privately):

```dotenv
LLM_PROVIDER=openai_compatible
LLM_MODEL=muse-spark-1.3-contributor
LLM_BASE_URL=https://api.meta.ai/v1
LLM_API=responses
LLM_REASONING_EFFORT=minimal
LLM_TIMEOUT_S=20
```

`LLM_PROVIDER=disabled` keeps analytics deterministic. The default `auto` preserves legacy Anthropic-before-OpenAI key selection: `LLM_MODEL` overrides `ASK_MODEL` for Anthropic and the legacy `gpt-4o-mini` default for OpenAI. Explicit provider selection requires a model and that provider's credential; no cross-provider failover occurs.

SDK clients reuse connections and close on shutdown. Generation uses `LLM_TIMEOUT_S=12` (1–20 seconds), no automatic retries, and `LLM_MAX_OUTPUT_TOKENS=4096` (256–16384). OpenAI/compatible endpoints accept optional `LLM_REASONING_EFFORT` (`minimal`, `low`, `medium`, `high`, `xhigh`) where the model supports it; empty uses model defaults. Minimal effort helps keep Muse's interactive SQL calls within the timeout. Reasoning tokens share the output budget with text. Empty, refused, or truncated output returns a deterministic fallback. Responses requests set `store=false`; provider retention policies still apply. Diagnostics omit prompts, response bodies, endpoints, and credentials. Database execution has its own timeout; these are not an overall request deadline.

Compose does not forward provider settings by default; add the selected settings to the API service as described in [operations](operations.md).

## Execution

1. Parse intent and UTC window. Confident common intents execute deterministic services.
2. A lower-confidence request can ask the provider for SQL against the fixed events schema and current dialect.
3. Parse a single SELECT/WITH AST; reject mutation/locks, unapproved functions, schemas and physical relations other than events. Check tenant/date/metric alignment.
4. Rewrite **every** physical events reference with bound project, selected time window and system-event exclusion predicates. The boundary is enforced even if generated SQL uses OR, joins, unions or CTEs.
5. Execute using a separate connection. SQLite authorizer and progress handler prevent unauthorized reads/writes and cancel expensive queries. PostgreSQL read-only transactions and statement timeout constrain execution. Fetch a configured row cap and report truncation.
6. Rules score structural/semantic checks. Accepted rows receive deterministic narration. There is no second model call over rows that could invent supporting numbers.
7. Missing provider, unsupported SQL, timeout, or failed validation produces a caveated deterministic fallback. The API returns evidence/coverage and exposes SQL for successful generated queries.

The score is **not calibrated answer correctness**. Table isolation and read-only execution do not guarantee the correct denominator, attribution model, revenue definition or cohort semantics. Mixed-currency money questions avoid SQL rather than allowing accidental sums. The prompt excludes blank visitor IDs and system events and includes metric/time guidance.

The provider receives a question, schema, project identifier and range, not database credentials or connectivity. Customer-supplied question text can contain sensitive information. Configure appropriate provider/data policies before hosting. Deterministic answers work without a provider.

## Verification layers

- Service regression tests establish metric arithmetic, UTC windows and chronology.
- SQL tests exercise aliases, CTEs, joins, unions, widened filters, unknown relations, unsafe functions, time boundaries, truncation and cancellation.
- `test_agentic_eval.py` uses scripted SQL for a question corpus. It verifies machinery/routing and narration, not a real model's generation ability.
- SDK contract tests use mocked HTTP transports to check real request serialization, text extraction, refusals/truncation, timeouts, and failures without consuming provider quota.
- The opt-in live tier runs six synthetic cases through real stdio MCP, an isolated API/database, and the configured provider. It checks five exact metric results, tenant/system-event isolation, and unsupported-question fallback. Run `METRICAIRN_LIVE_EVAL=1 uv run pytest -c pyproject.toml -q -s apps/api/tests/test_agentic_eval.py -k live`; this consumes provider quota. No customer data is used.
- PostgreSQL integration runs with `TEST_POSTGRES_URL`. A skipped live tier is not evidence of provider quality.

Before customer promises, expand an independently labeled corpus across sparse data, missing identity, mixed currencies, denominator ambiguity, unsupported intents and adversarial questions. Record exact query acceptance, metric correctness, abstention, latency and provider cost by model/version. A small passing corpus does not establish general provider accuracy or per-answer cost.
