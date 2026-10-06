"""Provider adapters for SQL generation; unavailable calls return None.

Only SQL generation uses a model. SQL assessment and result narration are
local and deterministic. Explicit selection never fails over to another provider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

from app import __version__
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)
    api: str = "responses"
    base_url: str = ""
    timeout: float = 12
    max_tokens: int = 4096
    reasoning_effort: str | None = None


class IncompleteResponse(ValueError):
    """Refused, empty, or truncated model output must not reach SQL execution."""


_clients: dict[ProviderConfig, Any] = {}
_client_lock = Lock()


def provider_config(settings: Settings) -> ProviderConfig | None:
    """Resolve one provider; auto preserves legacy Anthropic-before-OpenAI selection."""
    provider = settings.llm_provider
    model = settings.llm_model.strip()
    if provider == "disabled":
        return None
    if provider == "auto":
        if settings.anthropic_api_key:
            provider = "anthropic"
            model = model or settings.ask_model
        elif settings.openai_api_key:
            provider = "openai"
            model = model or "gpt-4o-mini"
        else:
            return None
    key = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "google": settings.gemini_api_key,
        "openai_compatible": settings.llm_api_key,
    }[provider]
    if not key or not key.strip() or not model:
        logger.warning("LLM configuration incomplete provider=%s", provider)
        return None
    base_url = settings.llm_base_url.rstrip("/") if provider == "openai_compatible" else ""
    if provider == "openai_compatible":
        try:
            url = urlsplit(base_url)
        except ValueError:
            logger.warning("LLM compatible endpoint invalid")
            return None
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not (
                url.scheme == "https"
                or (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})
            )
        ):
            logger.warning("LLM compatible endpoint invalid")
            return None
    return ProviderConfig(
        provider=provider,
        model=model,
        api_key=key.strip(),
        api=settings.llm_api if provider == "openai_compatible" else "responses",
        base_url=base_url,
        timeout=settings.llm_timeout_s,
        max_tokens=settings.llm_max_output_tokens,
        reasoning_effort=settings.llm_reasoning_effort or None,
    )


def _make_client(config: ProviderConfig):
    # Lazy SDK imports keep deterministic deployments and startup inexpensive.
    if config.provider == "anthropic":
        from anthropic import Anthropic

        return Anthropic(
            api_key=config.api_key,
            base_url="https://api.anthropic.com",
            timeout=config.timeout,
            max_retries=0,
        )
    if config.provider == "google":
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=config.api_key,
            vertexai=False,
            http_options=types.HttpOptions(
                timeout=int(config.timeout * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
                headers={"x-goog-api-client": f"metricairn/{__version__}"},
            ),
        )
    from openai import OpenAI

    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url or "https://api.openai.com/v1",
        timeout=config.timeout,
        max_retries=0,
    )


def _client(config: ProviderConfig):
    with _client_lock:
        if config not in _clients:
            _clients[config] = _make_client(config)
        return _clients[config]


def close_clients() -> None:
    """Release pooled connections during application shutdown."""
    with _client_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        try:
            client.close()
        except Exception as error:
            logger.warning("LLM client close failed error_type=%s", type(error).__name__)


def _complete(config: ProviderConfig, system: str, user: str) -> str:
    client = _client(config)
    if config.provider == "anthropic":
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason not in {"end_turn", "stop_sequence"}:
            raise IncompleteResponse()
        text = "\n".join(block.text for block in response.content if block.type == "text")
    elif config.provider == "google":
        from google.genai import types

        response = client.models.generate_content(
            model=config.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=config.max_tokens,
                candidate_count=1,
            ),
        )
        if not response.candidates or response.candidates[0].finish_reason != "STOP":
            raise IncompleteResponse()
        content = response.candidates[0].content
        text = "\n".join(
            part.text
            for part in (content.parts if content else []) or []
            if part.text and not part.thought
        )
    elif config.api == "responses":
        response = client.responses.create(
            model=config.model,
            instructions=system,
            input=user,
            max_output_tokens=config.max_tokens,
            store=False,
            **(
                {"reasoning": {"effort": config.reasoning_effort}}
                if config.reasoning_effort
                else {}
            ),
        )
        if response.status != "completed" or any(
            part.type == "refusal"
            for item in response.output
            if item.type == "message"
            for part in item.content
        ):
            raise IncompleteResponse()
        text = response.output_text
    else:
        response = client.chat.completions.create(
            model=config.model,
            max_completion_tokens=config.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **({"reasoning_effort": config.reasoning_effort} if config.reasoning_effort else {}),
        )
        if not response.choices:
            raise IncompleteResponse()
        choice = response.choices[0]
        if choice.finish_reason != "stop" or choice.message.refusal:
            raise IncompleteResponse()
        text = choice.message.content
    if not isinstance(text, str) or not text.strip():
        raise IncompleteResponse()
    return text.strip()


def complete_text(system: str, user: str) -> str | None:
    """Return plain model text, or None for a deterministic caller fallback."""
    config = provider_config(get_settings())
    if config is None:
        return None
    try:
        return _complete(config, system, user)
    except Exception as error:
        # Never log exception strings, prompts, response bodies, endpoints, or keys.
        status = getattr(error, "status_code", None)
        logger.warning(
            "LLM generation failed provider=%s error_type=%s status=%s",
            config.provider,
            type(error).__name__,
            status if isinstance(status, int) else None,
        )
        return None


def llm_available() -> bool:
    return provider_config(get_settings()) is not None
