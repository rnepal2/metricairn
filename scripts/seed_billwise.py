#!/usr/bin/env python3
"""Seed the Billwise demo — a fictional $18k MRR invoicing SaaS for freelancers,
run solo by founder "Maya Chen". This is AgentLens's ICP: an indie SaaS founder
who currently duct-tapes Plausible + gut feel.

The 60-day dataset tells a true-to-life story with three beats:
  1. Steady growth + a Product Hunt launch spike (day -25) → anomaly: spike.
  2. A botched Stripe key rotation (days -7..-4) → ALL payments fail for 4 days
     while signups and traffic stay normal → anomaly: dip. The demo moment:
     "revenue went to $0 while signups held — checkout is broken, not demand."
  3. One hero blog post (/blog/invoice-template-excel) quietly drives a third
     of signups, tracked via utm_campaign=invoice-template-guide → the
     content-ROI demo moment.

Usage:  apps/api/.venv/bin/python scripts/seed_billwise.py [API_URL]
Idempotent: deletes any existing Billwise project first.
The demo dashboard page uses a deterministic read key (see DEMO_READ_KEY).
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DEMO_READ_KEY = "alr_bw_demo_9f2k7q4x1m8z3d6v"

random.seed(20261003)

PAGES = ["/", "/pricing", "/features", "/templates", "/blog",
         "/blog/invoice-template-excel", "/blog/freelancer-tax-checklist",
         "/docs", "/about", "/changelog"]
PAGE_W = [0.26, 0.20, 0.12, 0.08, 0.10, 0.09, 0.05, 0.05, 0.03, 0.02]
HERO_POST = "/blog/invoice-template-excel"

SOURCES = [
    ("", "", 0.28),
    ("https://www.google.com/search", "google", 0.30),
    ("https://x.com", "twitter", 0.10),
    ("https://github.com", "github", 0.06),
    ("https://news.ycombinator.com", "hackernews", 0.06),
    ("https://www.producthunt.com", "producthunt", 0.04),
    ("https://linkedin.com", "linkedin", 0.06),
    ("https://maya-chen-newsletter.beehiiv.com", "newsletter", 0.10),
]
DEVICES = [("desktop", "Chrome", "Windows", 0.36), ("desktop", "Chrome", "macOS", 0.20),
           ("desktop", "Safari", "macOS", 0.08), ("mobile", "Safari", "iOS", 0.18),
           ("mobile", "Chrome", "Android", 0.12), ("desktop", "Firefox", "Linux", 0.04),
           ("tablet", "Safari", "iOS", 0.02)]


def pick(weighted):
    r = random.random()
    acc = 0.0
    for item in weighted:
        acc += item[-1]
        if r <= acc:
            return item
    return weighted[-1]


def main() -> None:
    http = httpx.Client(timeout=60, trust_env=False)

    # Idempotent: wipe any previous Billwise seed (direct DB, cascade).
    import os

    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "api"))
    sys.path.insert(0, "apps/api")
    from app.core.database import SessionLocal, init_db
    from app.core.security import _hash
    from app.models import ApiKey, Project

    init_db()
    db = SessionLocal()
    for old in db.query(Project).filter(Project.name == "Billwise").all():
        db.delete(old)
    db.commit()

    print(f"→ creating Billwise project at {API}")
    p = http.post(f"{API}/api/v1/projects", json={"name": "Billwise", "domain": "billwise.io"}).json()
    project_id, write_key = p["id"], p["write_key"]
    headers = {"X-Write-Key": write_key}
    rec = db.query(ApiKey).filter(ApiKey.project_id == project_id, ApiKey.scopes == "read").first()
    rec.key_hash = _hash(DEMO_READ_KEY)
    rec.key_prefix = DEMO_READ_KEY[:8]
    rec.name = "demo-read"
    db.commit()
    db.close()

    def flush(events: list[dict]) -> None:
        for i in range(0, len(events), 400):
            r = http.post(f"{API}/api/v1/ingest", json={"events": events[i:i + 400]}, headers=headers)
            r.raise_for_status()

    now = datetime.now(timezone.utc)
    batch: list[dict] = []
    vid = 0
    bug_days = {7, 6, 5, 4}      # botched Stripe key rotation: ALL payments fail
    ph_day = 25                  # Product Hunt launch

    for ago in range(60, -1, -1):
        day = now - timedelta(days=ago)
        weekly = 0.62 if day.weekday() >= 5 else 1.0
        growth = 1 + (60 - ago) * 0.015
        spike = 4.0 if ago in (ph_day, ph_day - 1) else 1.0
        n_visitors = max(20, int(random.gauss(320 * weekly * growth * spike, 26)))

        for _ in range(n_visitors):
            vid += 1
            v, s = f"bw_v{vid}", f"bw_s{vid}"
            ref, src, _w = pick(SOURCES)
            if ago in (ph_day, ph_day - 1) and random.random() < 0.6:
                ref, src = "https://www.producthunt.com", "producthunt"
            dev, browser, os_, _w2 = pick(DEVICES)
            n_pv = min(6, 1 + int(random.expovariate(0.7)))
            base_ts = day.replace(hour=random.randint(8, 21), minute=random.randint(0, 59))
            entry = random.choices(PAGES, weights=PAGE_W)[0]
            hero_entry = entry == HERO_POST
            # Session UTM persistence (mirrors the tracker): the landing UTMs
            # stamp every later event, so signups/revenue attribute to campaigns.
            if hero_entry:
                sess_utm = "utm_campaign=invoice-template-guide&utm_source=blog&utm_medium=content"
            elif src and random.random() < 0.7:
                sess_utm = f"utm_source={src}&utm_medium={'cpc' if src == 'google' else 'social'}"
                if ago in (ph_day, ph_day - 1) and src == "producthunt":
                    sess_utm += "&utm_campaign=ph-launch"
            else:
                sess_utm = ""
            hit_pricing = False

            def with_utm(url: str) -> str:
                return url + ("?" + sess_utm if sess_utm else "")

            for j in range(n_pv):
                path = entry if j == 0 else random.choices(PAGES, weights=PAGE_W)[0]
                hit_pricing = hit_pricing or path == "/pricing"
                url = with_utm(f"https://billwise.io{path}")
                batch.append({
                    "name": "pageview", "url": url, "referrer": ref,
                    "session_id": s, "visitor_id": v, "device": dev,
                    "browser": browser, "os": os_,
                    "at": (base_ts + timedelta(minutes=j * 2)).isoformat(),
                })

            if hit_pricing:
                # High-intent content converts better: readers who arrived via the
                # invoice-template guide are problem-aware and sign up ~1.6x more.
                p_signup = 0.22 if hero_entry else 0.14
                p_paid = 0.60 if hero_entry else 0.50
                if random.random() < p_signup:
                    batch.append({"name": "signup", "url": with_utm("https://billwise.io/signup"),
                                  "referrer": "", "session_id": s, "visitor_id": v,
                                  "device": dev, "browser": browser,
                                  "at": (base_ts + timedelta(minutes=n_pv * 2 + 1)).isoformat()})
                    # The bug: botched Stripe key rotation → every payment fails,
                    # but signups and traffic continue normally.
                    if ago not in bug_days and random.random() < p_paid:
                        plan = 49 if random.random() < 0.35 else 19
                        batch.append({"name": "revenue", "url": with_utm("https://billwise.io/checkout"),
                                      "session_id": s, "visitor_id": v, "device": dev,
                                      "browser": browser, "revenue_amount": plan,
                                      "revenue_currency": "USD",
                                      "at": (base_ts + timedelta(minutes=n_pv * 2 + 3)).isoformat()})

        if len(batch) >= 400:
            flush(batch)
            batch = []
    if batch:
        flush(batch)

    # Funnel + timeline notes (demo read key)
    rh = {"X-Read-Key": DEMO_READ_KEY}
    http.post(f"{API}/api/v1/funnels", json={
        "name": "Signup → Paid",
        "steps": [{"kind": "page", "value": "/pricing"},
                  {"kind": "event", "value": "signup"},
                  {"kind": "event", "value": "revenue"}],
    }, headers=rh).raise_for_status()
    for text, days_ago in [("Product Hunt launch 🚀", ph_day),
                           ("Rotated Stripe publishable key (checkout deploy)", 7),
                           ("Rolled back Stripe key — payments restored", 3)]:
        http.post(f"{API}/api/v1/projects/{project_id}/notes", json={
            "text": text, "at": (now - timedelta(days=days_ago)).isoformat(),
        }, headers=rh).raise_for_status()

    print("\n✅ Billwise demo seeded.")
    print(f"   Project:  Billwise ({project_id})")
    print(f"   Demo key: {DEMO_READ_KEY}  (deterministic — the demo page uses this)")
    print("   Open the dashboard → 'Billwise demo' for the guided story.")


if __name__ == "__main__":
    main()
