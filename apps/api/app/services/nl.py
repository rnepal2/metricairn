"""Natural-language to analytics-plan.

Two paths:
1. Heuristic parser (always available) — handles the most common founder questions.
2. LLM planner (when ANTHROPIC_API_KEY or OPENAI_API_KEY is configured) — falls
   back to the heuristic parser on any failure.

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
    for pattern, fn in DATE_HINTS:
        m = re.search(pattern, q)
        if m:
            days = fn(m)
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)
            return start.isoformat(), end.isoformat()
    return None, None


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
        plan = {"action": action, "date_from": date_from, "date_to": date_to,
                "confidence": conf}
        plan.update(kw)
        return plan

    if any(w in q for w in ("anomal", "spike", "dip", "unusual", "weird")):
        if any(w in q for w in ("why", "what happened", "explain", "because", "cause")):
            return base("explain")
        return base("anomalies")
    # Comparison / multi-period questions need composed queries the ten fixed
    # actions can't express — route them to the agentic SQL path.
    if re.search(r"\bcompare\b|\bvs\.?\b|\bversus\b|difference between", q):
        return base("overview", conf=0.25)
    if any(w in q for w in ("funnel", "leak", "drop-off", "dropoff", "convert")):
        return base("funnels", segment_by=_funnel_segment(q))
    if any(w in q for w in ("content", "blog", "post", "article")):
        return base("breakdown", dimension="utm_campaign")
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
    if any(w in q for w in ("referrer", "referral", "traffic from", "where.*come from", "sources", "channels")):
        return base("breakdown", dimension="utm_source")
    if any(w in q for w in ("device", "mobile vs", "desktop")):
        return base("breakdown", dimension="device")
    if any(w in q for w in ("countr", "geograph", "where.*visitors")):
        return base("breakdown", dimension="country")
    if any(w in q for w in ("event", "clicked", "button", "signup", "sign up")):
        return base("breakdown", dimension="event")
    if any(w in q for w in ("bounce",)):
        return base("overview")
    if any(w in q for w in ("visitor", "traffic", "pageview", "how many", "growth", "trend")):
        return base("timeseries_smart")
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
