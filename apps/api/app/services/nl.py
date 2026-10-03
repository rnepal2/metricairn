"""Natural-language to analytics-plan.

Two paths:
1. Heuristic parser (always available) — handles the most common founder questions.
2. LLM planner (when ANTHROPIC_API_KEY or OPENAI_API_KEY is configured) — falls
   back to the heuristic parser on any failure.

A *plan* is a small JSON dict the ask router executes against the analytics
service; the MCP `ask` tool uses the same endpoint, so both surfaces stay in sync.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings

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


def heuristic_plan(question: str) -> dict:
    """Map common questions to structured plans. Returns a plan dict."""
    q = question.lower()
    date_from, date_to = _date_range(question)

    def base(action: str, **kw) -> dict:
        plan = {"action": action, "date_from": date_from, "date_to": date_to}
        plan.update(kw)
        return plan

    if any(w in q for w in ("anomal", "spike", "dip", "unusual", "weird")):
        return base("anomalies")
    if any(w in q for w in ("right now", "realtime", "real-time", "live", "currently")):
        return base("realtime")
    if "funnel" in q:
        return base("funnels")
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
    return base("overview")


PLAN_SCHEMA_HINT = """Return ONLY a JSON object with this shape:
{"action": one of [overview, timeseries_smart, breakdown, revenue, revenue_by_source, realtime, anomalies, funnels, mcp_usage],
 "dimension": optional one of [path, referrer, utm_source, utm_medium, utm_campaign, device, browser, os, country, event],
 "metric": optional one of [visitors, pageviews, sessions, events, revenue],
 "days": optional integer lookback window}
"""


def llm_plan(question: str) -> dict | None:
    settings = get_settings()
    try:
        if settings.anthropic_api_key:
            return _anthropic_plan(question, settings.anthropic_api_key, settings.ask_model)
        if settings.openai_api_key:
            return _openai_plan(question, settings.openai_api_key)
    except Exception:
        return None
    return None


def _anthropic_plan(question: str, api_key: str, model: str) -> dict | None:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": model,
            "max_tokens": 300,
            "messages": [
                {
                    "role": "user",
                    "content": f"You map product-analytics questions to query plans.\n{PLAN_SCHEMA_HINT}\nQuestion: {question}",
                }
            ],
        },
        timeout=20,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"]
    plan = json.loads(text[text.index("{") : text.rindex("}") + 1])
    return _normalize_llm_plan(plan)


def _openai_plan(question: str, api_key: str) -> dict | None:
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": f"You map product-analytics questions to query plans.\n{PLAN_SCHEMA_HINT}"},
                {"role": "user", "content": question},
            ],
        },
        timeout=20,
    )
    resp.raise_for_status()
    plan = json.loads(resp.json()["choices"][0]["message"]["content"])
    return _normalize_llm_plan(plan)


def _normalize_llm_plan(plan: dict) -> dict:
    days = plan.get("days")
    date_from = date_to = None
    if isinstance(days, int) and days > 0:
        end = datetime.now(timezone.utc)
        date_from, date_to = (end - timedelta(days=days)).isoformat(), end.isoformat()
    out = {"action": plan.get("action", "overview"), "date_from": date_from, "date_to": date_to}
    if plan.get("dimension"):
        out["dimension"] = plan["dimension"]
    if plan.get("metric"):
        out["metric"] = plan["metric"]
    return out


def plan(question: str) -> tuple[dict, str]:
    """Return (plan, planner_used)."""
    llm = llm_plan(question)
    if llm and llm.get("action"):
        return llm, "llm"
    return heuristic_plan(question), "heuristic"
