/** Billwise demo constants. DEMO_READ_KEY is deterministic (see scripts/seed_billwise.py).
 *  FALLBACK_* numbers are recomputed from the seeded data — refresh them after re-seeding.
 *  DEMO_TRANSCRIPT holds the real /ask responses (heuristic planner), captured
 *  2026-10-03 against the seeded dataset. */

export const DEMO_READ_KEY = 'alr_bw_demo_9f2k7q4x1m8z3d6v';

export const DEMO_FALLBACK = {
  // Moment 1 — the Stripe key outage (Sep 26–29, 4 days at $0)
  dip_window: 'Sep 26–29',
  dip_days: 4,
  dip_expected: 1473,
  dip_z: -4.98,
  bug_cause: 'a botched Stripe key rotation took every payment to $0 for 4 days',
  monthly_leak: 9800, // daily avg × 30 — what the outage would cost per month undetected
  // Moment 2 — content ROI (60-day attributed)
  hero_post: '/blog/invoice-template-excel',
  hero_signup_share: 7, // % of signups attributed to the hero post campaign
  hero_revenue: 1462, // attributed revenue, 60 days
  ph_revenue: 872, // the Product Hunt launch, for comparison
  // Moment 3 — funnel (60 days)
  funnel_entered: 5731,
  funnel_overall: 7.2,
  funnel_leak_step: 'pricing → signup',
  funnel_leak_conv: 15.0,
  // Baseline
  mrr: 10000,
};

export const DEMO_TRANSCRIPT = [
  {
    q: 'Why did revenue dip recently?',
    a: 'Revenue dip 2026-09-26 to 2026-09-29 (4 days): $0 vs ~$1,473 expected (z=-4.98). The drop hit every device, browser, and source at once. Pageviews held at 3,755 vs ~3,741 normally — traffic was fine, so this looks like a checkout or payment failure, not a demand problem. Timeline notes around that window: \'Rotated Stripe publishable key (checkout deploy)\' (2026-09-26); \'Rolled back Stripe key — payments restored\' (2026-09-30).',
    planner: 'heuristic',
  },
  {
    q: 'Which content actually drives trials?',
    a: "Top utm_campaign: 'invoice-template-guide' with 1,591 visitors (3,088 pageviews). Top by revenue: 'ph-launch' at 872.00 USD.",
    planner: 'heuristic',
  },
  {
    q: 'Where does checkout leak the most?',
    a: "1 funnel(s). Best converting: 'Signup → Paid' at 7.2%. 'Signup → Paid': 5,731 entered; /pricing (100.0%) → signup (15.0%) → revenue (7.2%). Biggest leak: → signup (15.0% step conversion).",
    planner: 'heuristic',
  },
];
