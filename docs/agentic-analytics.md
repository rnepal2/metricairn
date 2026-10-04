# Natural-language analytics

Common questions use a deterministic intent parser and tested aggregate services. The SQL route extends the vocabulary when an API provider is configured (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`) and `AGENTIC_SQL_ENABLED=true`.

1. Parse intent and UTC window. Confident common intents execute deterministic services.
2. A lower-confidence request can ask the provider for SQL against the fixed events schema and current dialect.
3. Parse a single SELECT/WITH AST; reject mutation/locks, unapproved functions, schemas and physical relations other than events. Check tenant/date/metric alignment.
4. Rewrite **every** physical events reference with bound project, selected time window and system-event exclusion predicates. The boundary is enforced even if generated SQL uses OR, joins, unions or CTEs.
5. Execute using a separate connection. SQLite authorizer and progress handler prevent unauthorized reads/writes and cancel expensive queries. PostgreSQL read-only transactions and statement timeout constrain execution. Fetch a configured row cap and report truncation.
6. Rules score structural/semantic checks. Accepted rows receive deterministic narration. There is no second model call over rows that could invent supporting numbers.
7. Missing provider, unsupported SQL, timeout, or failed validation produces a caveated deterministic fallback. The API returns evidence/coverage and exposes SQL for successful generated queries.

The score is **not calibrated answer correctness**. Table isolation and read-only execution do not guarantee the correct denominator, attribution model, revenue definition or cohort semantics. Mixed-currency money questions avoid SQL rather than allowing accidental sums. The prompt excludes blank visitor IDs and system events and includes metric/time guidance.

The provider receives a question, schema, project identifier and range, not credentials or database connectivity. Customer-supplied question text can contain sensitive information. Configure appropriate provider/data policies before hosting. Deterministic answers work without a provider.

## Verification layers

- Service regression tests establish metric arithmetic, UTC windows and chronology.
- SQL tests exercise aliases, CTEs, joins, unions, widened filters, unknown relations, unsafe functions, time boundaries, truncation and cancellation.
- `test_agentic_eval.py` uses scripted SQL for a question corpus. It verifies machinery/routing and narration, not a real model's generation ability.
- The live-provider tier runs only with an explicit provider key. PostgreSQL integration runs with `TEST_POSTGRES_URL`. Neither skipped tier is evidence of a successful live evaluation.

Before customer promises, expand an independently labeled corpus across sparse data, missing identity, mixed currencies, denominator ambiguity, unsupported intents and adversarial questions. Record exact query acceptance, metric correctness, abstention, latency and provider cost by model/version. An answer judged harmful should abstain rather than optimize a single accuracy average. No measured provider accuracy or per-answer cost is claimed in this version.
