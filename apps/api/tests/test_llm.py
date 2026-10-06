"""Exercise SDK serialization, responses, selection, and failures without network access."""

import json
from unittest.mock import Mock

import httpx2
import pytest
from app.core.config import Settings
from app.services import llm

SQL = "SELECT COUNT(*) AS n FROM events WHERE project_id = 'test'"


def settings(**kwargs):
    # Isolate from developer credentials and all environment-based LLM selection.
    return Settings(_env_file=None, llm_provider="disabled").model_copy(update=kwargs)


def test_legacy_selection_and_model_override():
    config = settings(llm_provider="auto", anthropic_api_key="a", openai_api_key="o")
    assert llm.provider_config(config).provider == "anthropic"
    assert llm.provider_config(config).model == config.ask_model
    config = config.model_copy(update={"anthropic_api_key": None})
    assert llm.provider_config(config).provider == "openai"
    assert llm.provider_config(config).model == "gpt-4o-mini"
    assert (
        llm.provider_config(config.model_copy(update={"llm_model": "selected"})).model == "selected"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"llm_provider": "openai", "anthropic_api_key": "other", "llm_model": "model"},
        {"llm_provider": "google", "gemini_api_key": "key"},
        {"llm_provider": "disabled", "openai_api_key": "key"},
        {"llm_provider": "openai_compatible", "llm_model": "model", "llm_api_key": "key"},
    ],
)
def test_missing_selected_configuration_never_uses_another_provider(changes, monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: settings(**changes))
    assert not llm.llm_available()
    assert llm.complete_text("system", "question") is None


@pytest.mark.parametrize(
    "endpoint,valid",
    [
        ("https://api.meta.ai/v1", True),
        ("http://127.0.0.1:11434/v1", True),
        ("http://example.test/v1", False),
        ("https://user:secret@example.test/v1", False),
        ("https://example.test/v1?api_key=secret", False),
        ("https://[", False),
    ],
)
def test_compatible_endpoint_configuration(endpoint, valid):
    config = settings(
        llm_provider="openai_compatible", llm_model="m", llm_api_key="key", llm_base_url=endpoint
    )
    assert bool(llm.provider_config(config)) is valid


def payload(provider, api="responses", *, status="completed"):
    if provider == "anthropic":
        return {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "test-model",
            "content": [{"type": "text", "text": SQL}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    if provider == "google":
        return {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": "private reasoning", "thought": True}, {"text": SQL}],
                    },
                    "finishReason": "STOP",
                }
            ]
        }
    if api == "chat_completions":
        return {
            "id": "chat_test",
            "object": "chat.completion",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": SQL},
                }
            ],
        }
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "model": "test-model",
        "status": status,
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": SQL, "annotations": []}],
            }
        ],
    }


def install_mock_client(monkeypatch, config, response):
    requests = []

    def handler(request):
        requests.append(request)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, int):
            return httpx2.Response(response, json={"error": {"message": "private body"}})
        return httpx2.Response(200, json=response)

    http = httpx2.Client(transport=httpx2.MockTransport(handler))
    if config.provider == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(
            api_key=config.api_key, http_client=http, max_retries=0, timeout=config.timeout
        )
    elif config.provider == "google":
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=config.api_key,
            vertexai=False,
            http_options=types.HttpOptions(
                httpx_client=http,
                timeout=int(config.timeout * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    else:
        from openai import OpenAI

        client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url or "https://api.openai.com/v1",
            http_client=http,
            max_retries=0,
            timeout=config.timeout,
        )
    monkeypatch.setattr(llm, "_make_client", lambda config: client)
    return requests


@pytest.mark.parametrize(
    "provider,api,path",
    [
        ("openai", "responses", "/v1/responses"),
        ("anthropic", "responses", "/v1/messages"),
        ("google", "responses", ":generateContent"),
        ("openai_compatible", "responses", "/v1/responses"),
        ("openai_compatible", "chat_completions", "/v1/chat/completions"),
    ],
)
def test_real_sdk_request_and_response_contract(monkeypatch, provider, api, path):
    config_settings = settings(
        llm_provider=provider,
        llm_model="test-model",
        llm_api=api,
        openai_api_key="openai-secret",
        anthropic_api_key="anthropic-secret",
        gemini_api_key="google-secret",
        llm_api_key="compatible-secret",
        llm_base_url="https://api.meta.ai/v1",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: config_settings)
    config = llm.provider_config(config_settings)
    requests = install_mock_client(monkeypatch, config, payload(provider, api))
    assert llm.llm_available()
    assert llm.complete_text("SQL rules", "Question") == SQL
    body = json.loads(requests[0].content)
    assert path in requests[0].url.path
    assert "SQL rules" in requests[0].content.decode()
    assert "Question" in requests[0].content.decode()
    assert "test-model" in str(requests[0].url) or body["model"] == "test-model"
    if provider == "anthropic":
        assert requests[0].headers["x-api-key"] == "anthropic-secret"
        assert body["max_tokens"] == 4096
    elif provider == "google":
        assert requests[0].headers["x-goog-api-key"] == "google-secret"
        assert body["generationConfig"]["maxOutputTokens"] == 4096
    else:
        assert requests[0].headers["authorization"] == "Bearer " + config.api_key
        if api == "responses":
            assert body["store"] is False and body["max_output_tokens"] == 4096
        else:
            assert body["max_completion_tokens"] == 4096
    # Reuses the same client; shutdown releases its connections.
    assert llm._client(config) is llm._client(config)
    llm.close_clients()
    assert not llm._clients


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
@pytest.mark.parametrize("error", [401, 429, 500, httpx2.ReadTimeout("secret prompt and key")])
def test_sdk_failures_abstain_without_retry_or_sensitive_diagnostics(
    monkeypatch, caplog, provider, error
):
    config_settings = settings(
        llm_provider=provider,
        llm_model="test-model",
        openai_api_key="secret",
        anthropic_api_key="secret",
        gemini_api_key="secret",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: config_settings)
    requests = install_mock_client(monkeypatch, llm.provider_config(config_settings), error)
    assert llm.complete_text("private schema", "private question") is None
    assert len(requests) == 1
    assert "LLM generation failed" in caplog.text
    for value in ("secret", "private body", "private schema", "private question"):
        assert value not in caplog.text


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "openai_compatible"])
def test_truncated_output_is_not_executed(monkeypatch, provider):
    config_settings = settings(
        llm_provider=provider,
        llm_model="test-model",
        llm_api="responses",
        openai_api_key="o",
        anthropic_api_key="a",
        gemini_api_key="g",
        llm_api_key="c",
        llm_base_url="https://test.local/v1",
    )
    response = payload(provider)
    if provider == "anthropic":
        response["stop_reason"] = "max_tokens"
    elif provider == "google":
        response["candidates"][0]["finishReason"] = "MAX_TOKENS"
    else:
        response["status"] = "incomplete"
    monkeypatch.setattr(llm, "get_settings", lambda: config_settings)
    install_mock_client(monkeypatch, llm.provider_config(config_settings), response)
    assert llm.complete_text("system", "question") is None


def test_production_client_options(monkeypatch):
    import anthropic
    import openai
    from google import genai

    base = llm.ProviderConfig(provider="openai", model="m", api_key="secret")
    for provider, module, name in (
        ("openai", openai, "OpenAI"),
        ("anthropic", anthropic, "Anthropic"),
        ("google", genai, "Client"),
    ):
        constructor = Mock()
        monkeypatch.setattr(module, name, constructor)
        llm._make_client(
            llm.ProviderConfig(provider=provider, model=base.model, api_key=base.api_key)
        )
        kwargs = constructor.call_args.kwargs
        if provider == "google":
            assert kwargs["http_options"].timeout == 12000
            assert kwargs["http_options"].retry_options.attempts == 1
        else:
            assert kwargs["timeout"] == 12 and kwargs["max_retries"] == 0
    assert "secret" not in repr(base)


@pytest.mark.parametrize(
    "provider,api",
    [
        ("openai", "responses"),
        ("anthropic", "responses"),
        ("google", "responses"),
        ("openai_compatible", "chat_completions"),
    ],
)
def test_refused_or_empty_output_abstains(monkeypatch, provider, api):
    config_settings = settings(
        llm_provider=provider,
        llm_model="test-model",
        llm_api=api,
        openai_api_key="o",
        anthropic_api_key="a",
        gemini_api_key="g",
        llm_api_key="c",
        llm_base_url="https://test.local/v1",
    )
    response = payload(provider, api)
    if provider == "anthropic":
        response["content"] = []
    elif provider == "google":
        response["candidates"] = []
    elif api == "responses":
        response["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot answer"}]
    else:
        response["choices"][0]["message"]["refusal"] = "Cannot answer"
    monkeypatch.setattr(llm, "get_settings", lambda: config_settings)
    install_mock_client(monkeypatch, llm.provider_config(config_settings), response)
    assert llm.complete_text("system", "question") is None


@pytest.mark.parametrize("api", ["responses", "chat_completions"])
def test_compatible_reasoning_control(monkeypatch, api):
    config_settings = settings(
        llm_provider="openai_compatible",
        llm_model="muse-model",
        llm_api=api,
        llm_api_key="test-secret",
        llm_base_url="https://api.meta.ai/v1",
        llm_reasoning_effort="low",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: config_settings)
    requests = install_mock_client(
        monkeypatch, llm.provider_config(config_settings), payload("openai_compatible", api)
    )
    assert llm.complete_text("system", "question") == SQL
    body = json.loads(requests[0].content)
    if api == "responses":
        assert body["reasoning"] == {"effort": "low"}
    else:
        assert body["reasoning_effort"] == "low"


def test_example_settings_load_without_credentials():
    config = Settings(_env_file=".env.example", llm_provider="auto")
    assert config.llm_reasoning_effort == ""
    assert llm.provider_config(config) is None
