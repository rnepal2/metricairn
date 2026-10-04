import { useEffect, useState } from 'react';
import { Bot, ArrowRight, AlertTriangle, TrendingUp, FileText, Filter, Check, X, Sparkles, KeyRound, Code2 } from 'lucide-react';
import { DEMO_READ_KEY, DEMO_FALLBACK as F, DEMO_TRANSCRIPT } from '@/lib/demo';
import { useApp } from '@/lib/store';
import { setReadKey, api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/badge';
import { TimeseriesChart, BarListChart } from '@/components/charts/charts';
import { fmtMoney } from '@/lib/utils';

const H = { 'X-Read-Key': DEMO_READ_KEY };

async function dj<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: H });
  if (!r.ok) throw new Error(`demo fetch failed: ${path}`);
  return r.json();
}

function useDemo<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => { fn().then(setData).catch(() => setData(null)); }, []);
  return data;
}

function Chat({ q, a, planner }: { q: string; a: string; planner: string }) {
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-slate-900 px-4 py-2.5 text-sm text-white">{q}</div>
      </div>
      <div className="flex gap-2.5">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white"><Bot className="h-4 w-4" /></div>
        <div className="max-w-[90%]">
          <div className="rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-2.5 text-sm leading-relaxed">{a}</div>
          <div className="mt-1 text-[11px] text-slate-400">answered from live data · planned by {planner}</div>
        </div>
      </div>
    </div>
  );
}

function Advantage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <Check className="h-5 w-5 shrink-0 text-emerald-600" />
      <p className="text-sm leading-relaxed text-emerald-900"><span className="font-semibold">The advantage: </span>{children}</p>
    </div>
  );
}

function PoweredBy({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-xl border border-slate-200 bg-white p-4">
      <Code2 className="h-4 w-4 shrink-0 text-slate-400" />
      <p className="text-xs leading-relaxed text-slate-500"><span className="font-semibold text-slate-700">Powered by: </span>{children}</p>
    </div>
  );
}

export function Demo() {
  const { setPage, setProject } = useApp();
  const [entering, setEntering] = useState(false);

  const anomalies = useDemo(() => dj<any[]>('/api/v1/query/anomalies?date_from=' + new Date(Date.now() - 60 * 864e5).toISOString()));
  const revenue = useDemo(() => dj<any>('/api/v1/query/revenue?date_from=' + new Date(Date.now() - 60 * 864e5).toISOString()));
  const campaigns = useDemo(() => dj<any[]>('/api/v1/query/breakdown?dimension=utm_campaign&limit=8&date_from=' + new Date(Date.now() - 60 * 864e5).toISOString()));
  const funnel = useDemo(async () => {
    const list = await dj<any[]>('/api/v1/funnels');
    const f = list.find((x) => x.name.includes('Signup')) ?? list[0];
    if (!f) return null;
    return dj<any>(`/api/v1/funnels/${f.id}/report?date_from=` + new Date(Date.now() - 60 * 864e5).toISOString());
  });

  async function openDashboard() {
    setEntering(true);
    try {
      setReadKey(DEMO_READ_KEY);
      const me = await api.me();
      setProject(me);
      setPage('overview');
    } catch {
      setEntering(false);
    }
  }

  const dip = (anomalies ?? []).find((a: any) => a.direction === 'dip');

  return (
    <div className="min-h-screen bg-white">
      {/* top bar */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white"><Bot className="h-4 w-4" /></div>
            <span className="text-sm font-bold">AgentLens</span>
            <Badge variant="secondary" className="ml-2">Live demo · simulated data</Badge>
          </div>
          <Button size="sm" onClick={openDashboard} disabled={entering}>
            <KeyRound /> {entering ? 'Opening…' : 'Open live dashboard'}
          </Button>
        </div>
      </header>

      {/* hero */}
      <section className="mx-auto max-w-5xl px-6 pb-10 pt-14">
        <Badge variant="info" className="mb-4">Customer story · Billwise</Badge>
        <h1 className="max-w-3xl text-4xl font-bold leading-tight tracking-tight">
          How Maya found a <span className="text-emerald-700">{fmtMoney(F.monthly_leak)}/mo</span> checkout bug in 90 seconds.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-600">
          Maya Chen runs <strong>Billwise</strong> — simple invoicing for freelancers,{' '}
          {fmtMoney(F.mrr)} MRR, team of one. On a Monday morning her revenue chart looked wrong.
          She didn't open a dashboard. She asked her AI agent.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button onClick={() => document.getElementById('moment-1')?.scrollIntoView({ behavior: 'smooth' })}>
            See the 3 moments <ArrowRight />
          </Button>
          <Button variant="outline" onClick={openDashboard}>Explore the live dashboard</Button>
        </div>
      </section>

      {/* moment 1 */}
      <section id="moment-1" className="border-t border-slate-100 bg-slate-50/50">
        <div className="mx-auto max-w-5xl space-y-5 px-6 py-12">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-500"><AlertTriangle className="h-4 w-4" /> MOMENT 1 · THE MONDAY ALERT</div>
          <h2 className="text-2xl font-bold">"Why did revenue dip last week?"</h2>
          <p className="max-w-2xl text-slate-600">
            AgentLens flagged a statistically significant dip overnight. Maya asked one question
            from her editor — no dashboards, no segment-building.
          </p>
          <div className="grid gap-5 lg:grid-cols-2">
            <Chat q={DEMO_TRANSCRIPT[0].q} a={DEMO_TRANSCRIPT[0].a} planner={DEMO_TRANSCRIPT[0].planner} />
            <Card>
              <CardHeader><CardTitle>Revenue — last 60 days</CardTitle></CardHeader>
              <CardContent>
                {revenue ? <TimeseriesChart data={revenue.timeseries} /> : <Skeleton className="h-64" />}
                {dip && (
                  <p className="mt-2 text-xs text-slate-500">
                    Detected dip: <strong>{dip.date_end ? `${dip.date} → ${dip.date_end} (${dip.days} days)` : dip.date}</strong>{' '}
                    — {dip.value} vs ~{dip.expected} expected (z = {dip.z_score}).
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
          <Advantage>
            From "revenue is down" to "{F.bug_cause}" in one question —{' '}
            <strong>90 seconds</strong> instead of an afternoon in GA4 segments. Maya shipped the fix
            before lunch and stopped a {fmtMoney(F.monthly_leak)}/mo leak.
          </Advantage>
          <PoweredBy>
            Two lines in her checkout handler firing <code className="font-mono">revenue</code> events
            with <code className="font-mono">revenue_amount</code> — plus the timeline note her agent
            wrote when she rotated the Stripe key. No Stripe OAuth, no database access: AgentLens only
            ever sees what Maya sends it.
          </PoweredBy>
        </div>
      </section>

      {/* moment 2 */}
      <section className="border-t border-slate-100">
        <div className="mx-auto max-w-5xl space-y-5 px-6 py-12">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-500"><FileText className="h-4 w-4" /> MOMENT 2 · CONTENT ROI</div>
          <h2 className="text-2xl font-bold">"Which content actually drives trials?"</h2>
          <p className="max-w-2xl text-slate-600">
            Maya writes a blog post every week but never knew which ones pay. AgentLens attributes
            signups and revenue back to campaigns — the tracker persists landing UTMs for the
            whole session, so even clean checkout URLs credit the content that started it.
          </p>
          <div className="grid gap-5 lg:grid-cols-2">
            <Chat q={DEMO_TRANSCRIPT[1].q} a={DEMO_TRANSCRIPT[1].a} planner={DEMO_TRANSCRIPT[1].planner} />
            <Card>
              <CardHeader><CardTitle>Attributed revenue by campaign (60 days)</CardTitle></CardHeader>
              <CardContent>
                {campaigns ? (
                  <BarListChart
                    data={(campaigns as unknown as Record<string, unknown>[]).filter((r) => r['value'] !== '(not set)')}
                    xKey="value"
                    yKey="revenue"
                  />
                ) : <Skeleton className="h-64" />}
                <p className="mt-2 text-xs text-slate-500">
                  Her Product Hunt launch drove {fmtMoney(F.ph_revenue)} — one three-year-old
                  template post drove {fmtMoney(F.hero_revenue)}, every month, on autopilot.
                </p>
              </CardContent>
            </Card>
          </div>
          <Advantage>
            One template post drives <strong>{F.hero_signup_share}% of signups</strong> and beat her
            biggest launch ever on attributed revenue. Maya stopped guessing what to write and
            doubled down on templates — the kind of answer Plausible and Fathom don't give you.
          </Advantage>
          <PoweredBy>
            The 2.3KB tracker persisting landing UTMs for the whole session — every event carries{' '}
            <code className="font-mono">utm_campaign</code>, so even clean checkout URLs credit the
            content that started the visit. One snippet, zero configuration.
          </PoweredBy>
        </div>
      </section>

      {/* moment 3 */}
      <section className="border-t border-slate-100 bg-slate-50/50">
        <div className="mx-auto max-w-5xl space-y-5 px-6 py-12">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-500"><Filter className="h-4 w-4" /> MOMENT 3 · THE FUNNEL</div>
          <h2 className="text-2xl font-bold">"Where does checkout leak the most?"</h2>
          <p className="max-w-2xl text-slate-600">
            Pricing → signup → paid, computed in order per visitor. Maya checks it every Friday —
            or just asks.
          </p>
          <div className="grid gap-5 lg:grid-cols-2">
            <Chat q={DEMO_TRANSCRIPT[2].q} a={DEMO_TRANSCRIPT[2].a} planner={DEMO_TRANSCRIPT[2].planner} />
            <Card>
              <CardHeader><CardTitle>{funnel ? funnel.name : 'Signup → Paid'}</CardTitle></CardHeader>
              <CardContent>
                {!funnel ? <Skeleton className="h-64" /> : (
                  <div className="space-y-3">
                    {funnel.steps.map((s: any, i: number) => (
                      <div key={i}>
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-mono text-xs">{s.step.value}</span>
                          <span className="font-semibold">{s.visitors.toLocaleString()} · {(s.conversion_from_start * 100).toFixed(1)}%</span>
                        </div>
                        <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-slate-200">
                          <div className="h-full rounded-full bg-slate-900" style={{ width: `${Math.max(2, s.conversion_from_start * 100)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
          <Advantage>
            The same funnel her agent queries from the MCP server —{' '}
            <strong>"which step leaks most on mobile?"</strong> is one question away, in the tool
            she already works in.
          </Advantage>
          <PoweredBy>
            The <code className="font-mono">Signup → Paid</code> funnel Maya defined in one minute,
            fed by <code className="font-mono">signup</code> events from the tracker. The agent reads
            the same funnel definition — no per-customer tuning, because there is no per-customer schema.
          </PoweredBy>
        </div>
      </section>

      {/* comparison */}
      <section className="border-t border-slate-100">
        <div className="mx-auto max-w-5xl px-6 py-12">
          <h2 className="text-2xl font-bold">Monday morning, two ways</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <Card className="border-slate-200">
              <CardHeader><CardTitle className="flex items-center gap-2 text-slate-500"><X className="h-4 w-4" /> With GA4 / Plausible</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm text-slate-600">
                <p>Notice the dip on Monday's dashboard check.</p>
                <p>Build segments: mobile × Safari × last 7 days…</p>
                <p>Guess at causes, check deploys from memory.</p>
                <p className="font-medium text-slate-800">Afternoon gone. Bug ships another week.</p>
              </CardContent>
            </Card>
            <Card className="border-emerald-200 bg-emerald-50/50">
              <CardHeader><CardTitle className="flex items-center gap-2 text-emerald-800"><Sparkles className="h-4 w-4" /> With AgentLens</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm text-emerald-900">
                <p>Anomaly alert arrives overnight, automatically.</p>
                <p>One question: "why did revenue dip last week?"</p>
                <p>Grounded answer: {F.dip_window} — every payment at $0, traffic normal, deploy named.</p>
                <p className="font-medium">Fixed before lunch. {fmtMoney(F.monthly_leak)}/mo saved.</p>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-8 bg-slate-900 text-white">
            <CardContent className="flex flex-col items-start gap-4 pt-6 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-2 text-lg font-bold"><TrendingUp className="h-5 w-5" /> This demo runs on live data.</div>
                <p className="mt-1 max-w-xl text-sm text-slate-300">
                  Everything above queries the real API. Open the dashboard with the demo key,
                  ask the AI anything, or connect the MCP server and ask from your own agent.
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={openDashboard}>Open live dashboard</Button>
                <Button variant="outline" className="border-slate-700 bg-transparent text-white hover:bg-slate-800" onClick={() => setPage('settings')}>
                  Get the snippet
                </Button>
              </div>
            </CardContent>
          </Card>
          <p className="mt-4 text-center text-[11px] text-slate-400">
            Billwise is a fictional company; all data is simulated by scripts/seed_billwise.py.
          </p>
        </div>
      </section>
    </div>
  );
}
