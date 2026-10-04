# Maya Chen at Billwise

**Fictional worked example.** Maya is the solo founder of Billwise, an invoicing app for freelancers. The demo uses simulated events; its displayed counts and charts are calculated by Metricairn’s API. No customer endorsement, measured time saving, or financial outcome is claimed.

![Maya’s Billwise walkthrough with API-computed simulated data](../assets/billwise-demo.png)

## Monday’s questions

| Question | Workflow | Decision supported |
|---|---|---|
| What changed this week? | Compare pageviews with the preceding seven days; inspect source/device/browser/path contributions and collection coverage | Choose a segment and verify collection before interpreting the change |
| Which content deserves attention? | Query `signup` occurrences by `utm_campaign`; inspect missing tags and repeat events | Identify campaigns to examine; tagged signups are an association, not causal ROI |
| Are visitors converting and returning? | Inspect the ordered funnel, Account signup goal, and weekly retention | Separate traffic growth from conversion and return activity |
| What should I check next? | Export the report, or save immutable evidence and a review note with management access | Keep the observation, hypothesis, next check, and later decision together |

Example agent request: “Investigate Billwise’s pageview change over the last seven days. Check collection coverage, show the largest changed segments, and give me the next checks. Then report signup conversion and returning visitor cohorts.” The MCP server uses the same API definitions as the dashboard.

## Run the example

From a source checkout, with Python 3.12, Node.js 22, uv, and Make:

```bash
make setup
make build
make api                         # leave running in terminal 1
uv run python scripts/seed_billwise.py  # terminal 2, same repository root/database
```

Open **http://localhost:8000/?demo=billwise**, or select **“Explore the simulated Billwise demo”** on the login screen. The story opens without entering a key; “Explore dashboard” connects to the seeded project with read access. The story also links directly to signup goals and retention. Seeding replaces only the existing public demo project. Never use its shared read key for real customer data.

The dataset includes traffic sources/campaigns, repeat visitors, signup events, an ordered funnel, an Account signup goal, and timeline notes. Existing recorded-payment events are also included as optional historical context; this walkthrough requires no payment integration. For agent access, use the [MCP configuration](../../README.md#connect-an-agent) with demo read key `alr_bw_demo_9f2k7q4x1m8z3d6v`.

## Boundaries

A missing source tag is visible as `(not set)`. Goal conversion uses visitors with a pageview followed by signup; repeat signup events count once per visitor. Retention uses first recorded activity and leaves incomplete weeks blank. Nearby timeline notes do not establish cause. Saving a fixed query freezes its newly computed evidence; later activity does not rewrite the record. See [metric definitions](../trust-and-data.md).
