"""Natural-language to analytics-plan.

Intent classification is deterministic. Lower-confidence questions are routed
by the ask endpoint to guarded SQL generation when a provider is configured.

A *plan* is a small JSON dict the ask router executes against the analytics
service; the MCP `ask` tool uses the same endpoint, so both surfaces stay in sync.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

DATE_HINTS = [
    (r"last (\d+) days?", lambda m: int(m.group(1))),
    (r"past (\d+) days?", lambda m: int(m.group(1))),
    (r"last week", lambda m: 7),
    (r"yesterday", lambda m: 1),
    (r"this month", lambda m: 30),
    (r"last month", lambda m: 30),
]


def _date_range(question: str) -> tuple[str | None, str | None]:
    q = question.lower()
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    compared = re.search(r"(?:last|past) (\d+) days?.*(?:vs|versus|before)", q)
    if compared:
        days = min(183, max(1, int(compared.group(1))))
        start, end = now - timedelta(days=2 * days), now
    elif "this month" in q and "last month" in q:
        start, end = (today.replace(day=1) - timedelta(days=1)).replace(day=1), now
    elif "yesterday" in q:
        start, end = today - timedelta(days=1), today
    elif "last month" in q and "this month" not in q:
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
    elif "this month" in q and "last month" not in q:
        start, end = today.replace(day=1), now
    elif "last week" in q:
        end = today - timedelta(days=today.weekday())
        start = end - timedelta(days=7)
    elif re.search(r"\btoday\b", q):
        start, end = today, now
    else:
        match = re.search(r"(?:last|past) (\d+) days?", q)
        if not match:
            return None, None
        days = min(366, max(1, int(match.group(1))))
        start, end = now - timedelta(days=days), now
    return start.isoformat(), end.isoformat()


_FUNNEL_SEGMENTS = [
    (("device", "mobile", "desktop", "tablet"), "device"),
    (("browser", "chrome", "safari", "firefox"), "browser"),
    (("utm_source", "source", "channel"), "utm_source"),
    (("utm_medium", "medium"), "utm_medium"),
    (("utm_campaign", "campaign"), "utm_campaign"),
    (("country", "countries", "geography"), "country"),
    (("os", "operating system"), "os"),
]


def _funnel_segment(question: str) -> str | None:
    """Detect a segment dimension in a funnel question ('which device converts
    best' → 'device'). Returns None when no segment is named."""
    q = question.lower()
    for keywords, dimension in _FUNNEL_SEGMENTS:
        for k in keywords:
            if re.search(rf"\b{re.escape(k)}\b", q):
                return dimension
    return None


def heuristic_plan(question: str) -> dict:
    """Map common questions to structured plans. Returns a plan dict with a
    ``confidence`` key: 0.85 when a specific rule matched, 0.25 on the generic
    fallthrough. The ask router uses it to decide between the deterministic
    fast path and the agentic SQL path."""
    q = question.lower()
    date_from, date_to = _date_range(question)

    def base(action: str, conf: float = 0.85, **kw) -> dict:
        plan = {"action": action, "date_from": date_from, "date_to": date_to, "confidence": conf}
        plan.update(kw)
        return plan

    if any(w in q for w in ("anomal", "spike", "dip", "unusual", "weird")):
        if any(w in q for w in ("why", "what happened", "explain", "because", "cause")):
            return base("explain")
        return base("anomalies")
    # Comparison / multi-period questions need composed queries the ten fixed
    # actions can't express — route them to the agentic SQL path. Each pattern
    # below is a *class* of compositional question (comparisons, moving
    # averages, per-unit ratios, percentages, time-part groupings, negations,
    # destructive verbs), not a per-question hack: the heuristic's job is now
    # "answer exactly what I can; punt the rest to the agent".
    _LONGTAIL_HINTS = [
        r"\bcompare\b",
        r"\bvs\.?\b",
        r"\bversus\b",
        r"difference between",
        r"\bmoving average\b",
        r"\bper\b.{0,20}\b(visitor|user|customer|session)\b",
        r"\bpercent\b",
        r"\bpercentage\b",
        r"\bratio\b",
        r"\bday of week\b",
        r"\bhour of day\b",
        r"\bnever\b",
        r"\bdelete\b",
        r"\bdrop\b",
    ]
    if any(re.search(p, q) for p in _LONGTAIL_HINTS):
        return base("overview", conf=0.25)
    if any(w in q for w in ("funnel", "leak", "drop-off", "dropoff", "convert")):
        return base("funnels", segment_by=_funnel_segment(q))
    if "revenue" in q and any(w in q for w in ("campaign", "content", "blog", "article")):
        return base("breakdown", dimension="utm_campaign", order_by="revenue")
    if any(w in q for w in ("content", "blog", "post", "article")):
        return base("overview", conf=0.25)
    if any(w in q for w in ("how many", "number of", "count")) and any(
        w in q for w in ("signup", "sign up")
    ):
        return base("event_count", event_name="signup")
    if any(w in q for w in ("right now", "realtime", "real-time", "live", "currently")):
        return base("realtime")
    if "funnel" in q:
        return base("funnels", segment_by=_funnel_segment(q))
    if "revenue" in q and any(w in q for w in ("source", "channel", "utm", "where", "from")):
        return base("revenue_by_source")
    if "revenue" in q:
        return base("revenue")
    if any(w in q for w in ("top pages", "most visited", "popular pages", "best pages")):
        return base("breakdown", dimension="path")
    if re.search(r"where.*(?:come from|visitors)", q) or any(
        w in q for w in ("referrer", "referral", "traffic from", "sources", "channels")
    ):
        return base("breakdown", dimension="utm_source")
    if any(w in q for w in ("device", "mobile vs", "desktop")):
        return base("breakdown", dimension="device")
    if "browser" in q:
        return base("breakdown", dimension="browser")
    if any(w in q for w in ("countr", "geograph", "where.*visitors")):
        return base("breakdown", dimension="country")
    if any(w in q for w in ("event", "clicked", "button", "signup", "sign up")):
        return base("breakdown", dimension="event")
    if any(w in q for w in ("bounce",)):
        return base("overview")
    if any(w in q for w in ("visitor", "traffic", "pageview", "how many", "growth", "trend")):
        metric = "pageviews" if "pageview" in q else "sessions" if "session" in q else "visitors"
        return base("timeseries_smart", metric=metric)
    if "mcp" in q and any(w in q for w in ("usage", "tool", "agent")):
        return base("mcp_usage")
    return base("overview", conf=0.25)


def plan(question: str) -> tuple[dict, str, float]:
    """Return (plan, planner_used, confidence).

    Intent classification is heuristic-only by design. The old LLM
    intent-classifier was retired: an LLM picking among ten intents added
    latency for no quality gain on head questions, and the long tail is now
    served by the agentic SQL path (see services/sql_agent.py), where the
    LLM writes SQL against the fixed event schema instead. Low heuristic
    confidence is the signal that routes a question to the agentic path.
    """
    p = heuristic_plan(question)
    return p, "heuristic", p["confidence"]
