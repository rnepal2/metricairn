"""Tests for the MCP notes tools. Run with: .venv/bin/pytest -q"""

import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from metricairn_mcp import client as client_mod


class FakeHTTP:
    """Stub for httpx.Client: records requests, returns canned responses."""

    def __init__(self):
        self.posts = []
        self.gets = []

    def get(self, url, params=None, headers=None):
        self.gets.append(url)
        return FakeResp(
            {"project_id": "p123", "name": "Acme", "domain": "acme.test"}
            if url.endswith("/me")
            else []
        )

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url, json))
        return FakeResp({"ok": True, "id": "n1"})


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def api_client(monkeypatch):
    c = client_mod.MetricairnClient(
        api_url="http://x", read_key="alr_t", write_key="", management_key="alm_t"
    )
    fake = FakeHTTP()
    c._http = fake
    c._fake = fake
    return c


def test_project_id_cached(api_client):
    assert api_client.project_id() == "p123"
    assert api_client.project_id() == "p123"
    assert len(api_client._fake.gets) == 1  # second call served from cache


def test_add_note_posts_to_project_notes(api_client):
    out = api_client.add_note("Deployed new pricing page")
    assert out["ok"] is True
    url, body = api_client._fake.posts[0]
    assert url == "http://x/api/v1/projects/p123/notes"
    assert body == {"text": "Deployed new pricing page"}


def test_add_note_collapses_whitespace(api_client):
    api_client.add_note("  Deployed\n\n  new   pricing\tpage ")
    _, body = api_client._fake.posts[0]
    assert body["text"] == "Deployed new pricing page"


def test_add_note_rejects_empty_and_long(api_client):
    with pytest.raises(ValueError):
        api_client.add_note("   ")
    with pytest.raises(ValueError):
        api_client.add_note("x" * 501)


def test_list_notes(api_client):
    out = api_client.list_notes()
    assert out == []
    assert api_client._fake.gets[-1] == "http://x/api/v1/projects/p123/notes"


def _load_server(note_write: str):
    """Import server.py fresh with METRICAIRN_ENABLE_NOTE_WRITE controlled."""
    import metricairn_mcp.server as srv

    old = os.environ.get("METRICAIRN_ENABLE_NOTE_WRITE")
    os.environ["METRICAIRN_ENABLE_NOTE_WRITE"] = note_write
    try:
        return importlib.reload(srv)
    finally:
        if old is None:
            os.environ.pop("METRICAIRN_ENABLE_NOTE_WRITE", None)
        else:
            os.environ["METRICAIRN_ENABLE_NOTE_WRITE"] = old


def _tool_names(srv):
    # FastMCP exposes registered tools via the (private) _tool_manager in 1.x.
    mgr = srv.mcp._tool_manager
    tools = mgr._tools if hasattr(mgr, "_tools") else {}
    return set(tools)


def test_add_note_tool_opt_in():
    off = _load_server("0")
    names_off = _tool_names(off)
    assert "list_notes" in names_off
    assert "add_note" not in names_off

    on = _load_server("1")
    names_on = _tool_names(on)
    assert "add_note" in names_on


def test_add_note_tool_calls_client(monkeypatch):
    srv = _load_server("1")
    calls = []

    class FakeClient:
        def add_note(self, text):
            calls.append(text)
            return {"ok": True, "id": "n1"}

        def list_notes(self):
            return []

        def report_tool_call(self, *a, **k):
            pass

    monkeypatch.setattr(srv, "client", lambda: FakeClient())
    # timed_report passes through; call the plain impl function.
    out = json.loads(srv.add_note("Launched on PH"))
    assert out["ok"] is True
    assert calls == ["Launched on PH"]


def test_funnel_report_segment_param(api_client):
    seen = {}

    orig_get = api_client._http.get

    def rec_get(url, params=None, headers=None):
        seen["url"] = url
        seen["params"] = params or {}
        return orig_get(url, params, headers)

    api_client._http.get = rec_get
    api_client._project_id = "p1"

    api_client.funnel_report("f1", 30, segment_by="device")
    assert seen["url"] == "http://x/api/v1/funnels/f1/report"
    assert seen["params"]["segment_by"] == "device"

    api_client.funnel_report("f1", 30)
    assert "segment_by" not in seen["params"]
