#!/usr/bin/env python3
"""Seed a demo project ('Acme SaaS') with 30 days of plausible analytics data.

Usage:  python scripts/seed_demo.py [API_URL]
Then open the dashboard, paste the printed read key, and explore.
The data includes a launch spike (day -10) and an outage dip (day -4) so the
Alerts page and the `detect_anomalies` MCP tool have something to find.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
random.seed(42)

PAGES = ["/", "/pricing", "/features", "/blog", "/blog/ai-agents-guide", "/docs", "/about"]
PAGE_W = [0.30, 0.22, 0.15, 0.12, 0.08, 0.08, 0.05]
SOURCES = [
    ("", "", 0.30),  # direct
    ("https://www.google.com/search", "google", 0.28),
    ("https://x.com", "twitter", 0.12),
    ("https://github.com", "github", 0.10),
    ("https://news.ycombinator.com", "hackernews", 0.08),
    ("https://www.producthunt.com", "producthunt", 0.06),
    ("https://linkedin.com", "linkedin", 0.06),
]
DEVICES = [
    ("desktop", "Chrome", "Windows", 0.40),
    ("desktop", "Chrome", "macOS", 0.22),
    ("mobile", "Safari", "iOS", 0.20),
    ("mobile", "Chrome", "Android", 0.12),
    ("desktop", "Firefox", "Linux", 0.04),
    ("tablet", "Safari", "iOS", 0.02),
]


def pick(weighted):
    r = random.random()
    acc = 0.0
    for item in weighted:
        acc += item[-1]
        if r <= acc:
            return item
    return weighted[-1]


def main() -> None:
    http = httpx.Client(timeout=60, trust_env=False)  # bypass sandbox egress proxy for localhost
    print(f"→ creating project at {API}")
    p = http.post(
        f"{API}/api/v1/projects",
        headers={"X-Provisioning-Token": os.environ.get("PROVISIONING_TOKEN", "")},
        json={"name": "Acme SaaS", "domain": "acme.test"},
    ).json()
    project_id, write_key, read_key = p["id"], p["write_key"], p["read_key"]
    headers = {"X-Write-Key": write_key}

    def flush(events: list[dict]) -> None:
        events = [event for event in events if datetime.fromisoformat(event["at"]) <= now]
        for i in range(0, len(events), 400):  # API caps batches at 500
            r = http.post(
                f"{API}/api/v1/ingest", json={"events": events[i : i + 400]}, headers=headers
            )
            r.raise_for_status()

    now = datetime.now(timezone.utc)
    batch: list[dict] = []
    vid = 0

    for ago in range(30, -1, -1):
        day = now - timedelta(days=ago)
        dow = day.weekday()
        weekly = 0.62 if dow >= 5 else 1.0  # weekend dip
        growth = 1 + (30 - ago) * 0.02  # gentle growth
        spike = 3.0 if ago == 10 else 1.0  # launch spike
        dip = 0.35 if ago == 4 else 1.0  # outage dip
        n_visitors = int(random.gauss(70 * weekly * growth * spike * dip, 8))
        n_visitors = max(5, n_visitors)

        for _ in range(n_visitors):
            vid += 1
            v, s = f"v{vid}", f"s{vid}"
            ref, src, _w = pick(SOURCES)
            dev, browser, os_, _w2 = pick(DEVICES)
            n_pv = min(6, 1 + int(random.expovariate(0.7)))
            base_ts = day.replace(hour=random.randint(8, 20), minute=random.randint(0, 59))
            hit_pricing = False
            for j in range(n_pv):
                path = random.choices(PAGES, weights=PAGE_W)[0]
                hit_pricing = hit_pricing or path == "/pricing"
                url = f"https://acme.test{path}"
                if src and random.random() < 0.7:
                    url += f"?utm_source={src}&utm_medium={'cpc' if src == 'google' else 'social'}"
                batch.append(
                    {
                        "name": "pageview",
                        "url": url,
                        "referrer": ref,
                        "session_id": s,
                        "visitor_id": v,
                        "device": dev,
                        "browser": browser,
                        "os": os_,
                        "at": (base_ts + timedelta(minutes=j * 2)).isoformat(),
                    }
                )
            if hit_pricing and random.random() < 0.12:
                batch.append(
                    {
                        "name": "signup",
                        "url": "https://acme.test/signup",
                        "referrer": "",
                        "session_id": s,
                        "visitor_id": v,
                        "device": dev,
                        "at": (base_ts + timedelta(minutes=n_pv * 2 + 1)).isoformat(),
                    }
                )
                if random.random() < 0.45:
                    plan = 99 if random.random() < 0.3 else 29
                    batch.append(
                        {
                            "name": "revenue",
                            "url": "https://acme.test/checkout",
                            "session_id": s,
                            "visitor_id": v,
                            "device": dev,
                            "revenue_amount": plan,
                            "revenue_currency": "USD",
                            "at": (base_ts + timedelta(minutes=n_pv * 2 + 3)).isoformat(),
                        }
                    )
            if random.random() < 0.05:
                batch.append(
                    {
                        "name": "docs_search",
                        "url": "https://acme.test/docs",
                        "session_id": s,
                        "visitor_id": v,
                        "device": dev,
                        "at": (base_ts + timedelta(minutes=1)).isoformat(),
                    }
                )

        if len(batch) >= 400:
            flush(batch)
            batch = []

    if batch:
        flush(batch)

    # Funnel + timeline note (read key)
    rheaders = {"X-Management-Key": p["management_key"]}
    http.post(
        f"{API}/api/v1/funnels",
        json={
            "name": "Signup flow",
            "steps": [
                {"kind": "page", "value": "/pricing"},
                {"kind": "event", "value": "signup"},
                {"kind": "event", "value": "revenue"},
            ],
        },
        headers=rheaders,
    ).raise_for_status()
    http.post(
        f"{API}/api/v1/projects/{project_id}/notes",
        json={
            "text": "Launched v2 pricing page",
            "at": (now - timedelta(days=10)).isoformat(),
        },
        headers=rheaders,
    ).raise_for_status()
    http.post(
        f"{API}/api/v1/projects/{project_id}/notes",
        json={
            "text": "Outage: checkout down 3h",
            "at": (now - timedelta(days=4)).isoformat(),
        },
        headers=rheaders,
    ).raise_for_status()

    print("\n✅ Demo data seeded.")
    print(f"   Project:   Acme SaaS ({project_id})")
    print(f"   Write key: {write_key}")
    print(f"   Read key:  {read_key}")
    print(f"   Management key: {p['management_key']}")
    print("\nNext:")
    print("  1. cd apps/web && npm run dev   → http://localhost:5173")
    print("  2. Paste the read key, explore Overview / Revenue / Funnels / Ask / Alerts")
    print("  3. Try the MCP server (see README) and ask: 'any anomalies in the last 30 days?'")


if __name__ == "__main__":
    main()
