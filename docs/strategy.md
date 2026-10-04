# Product direction

**Hypothesis:** small teams can finish useful analytics investigations faster when their dashboard and coding agent share explicit definitions, collection checks, reproducible evidence, and a record of the decision. This is unvalidated positioning, not a demonstrated competitive moat.

PostHog already provides a [free hosted MCP](https://posthog.com/docs/model-context-protocol) for analytics, feature flags, error investigation, and other workflows. A shorter tool list is not an advantage by itself. Metricairn should earn adoption through a simpler self-hosted installation and better completion of a narrow job: “What changed, can I trust the data, where should I look, and what did we decide?”

## Validate the edge

1. Recruit 5–10 small SaaS/open-source teams with recurring signup or activation questions. Help them instrument one funnel and one goal; avoid a broad platform migration.
2. Compare the same investigation with their current tool: setup time, time to a defensible result, unsupported claims, and whether they can reproduce it a week later. Publish task definitions and failure cases.
3. Measure voluntary second-week use, completed investigations with evidence, and contributor fixes. Stars and downloads are distribution signals, not proof of recurring value.
4. Ship useful examples for popular frameworks and MCP clients, a public synthetic demo, and short investigation recipes. Support a few integrations well before adding many.

## Next differentiators

- Release markers and before/after checks with equivalent weekday windows and explicit uncertainty.
- Instrumentation contracts: expected events/properties, freshness checks, schema changes, and collection regressions.
- Portable investigation bundles and reproducible replay against a fixed synthetic dataset.
- Optional read-only adapters for existing analytics stores, allowing teams to try the workflow without replacing collection.

Validate each with real tasks before widening the product. Keep the implemented core MIT-licensed and free. Payment, billing, and transaction-system work is deferred; future funding does not require making the current product a paid tier.
