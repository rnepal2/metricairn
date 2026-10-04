"""Generic LLM text completion.

Tries Anthropic, then OpenAI, from server-side keys. Returns None when no key
is configured or the call fails — every caller must have a deterministic
fallback. Used by the agentic SQL path (generation, critic, narration).
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings


def _anthropic(system: str, user: str, api_key: str, model: str) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1200,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _openai(system: str, user: str, api_key: str) -> str:
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 1200,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def complete_text(system: str, user: str) -> str | None:
    """Return the model's raw text, or None when unavailable/failed."""
    settings = get_settings()
    try:
        if settings.anthropic_api_key:
            return _anthropic(system, user, settings.anthropic_api_key, settings.ask_model)
        if settings.openai_api_key:
            return _openai(system, user, settings.openai_api_key)
    except Exception:
        return None
    return None


def llm_available() -> bool:
    settings = get_settings()
    return bool(settings.anthropic_api_key or settings.openai_api_key)
