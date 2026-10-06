"""Offline tests must never consume a developer's configured provider key."""

import os

import pytest
from app.core.config import get_settings
from app.services import llm


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch):
    if os.environ.get("METRICAIRN_LIVE_EVAL") != "1":
        monkeypatch.setenv("LLM_PROVIDER", "disabled")
    get_settings.cache_clear()
    yield
    llm.close_clients()
    get_settings.cache_clear()
