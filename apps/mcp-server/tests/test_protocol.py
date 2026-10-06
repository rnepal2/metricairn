"""Real stdio MCP handshake and public tool contract."""

import os
import sys

import httpx
import pytest
from app.services.exploration import QueryPlan
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from metricairn_mcp.client import MetricairnClient, _range
from metricairn_mcp.schemas import AnalyticsPlan


@pytest.mark.asyncio
@pytest.mark.parametrize("telemetry", [False, True])
async def test_stdio_handshake_and_tool_effects(telemetry):
    env = dict(
        os.environ,
        METRICAIRN_ENABLE_NOTE_WRITE="0",
        METRICAIRN_ENABLE_INVESTIGATION_WRITE="0",
        METRICAIRN_WRITE_KEY="alw_unused" if telemetry else "",
    )
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", "metricairn_mcp"], env=env)
    ) as (receive, send):
        async with ClientSession(receive, send) as session:
            info = await session.initialize()
            assert info.serverInfo.name == "metricairn"
            assert "ask stores question text" in info.instructions
            tools = (await session.list_tools()).tools
            names = {tool.name for tool in tools}
            assert len(names) == 20
            assert {
                "run_query",
                "investigate_change",
                "retention_report",
                "goal_report",
                "get_investigation",
            } <= names
            assert not {"add_note", "save_investigation", "review_investigation"} & names
            for tool in tools:
                annotations = tool.annotations
                assert annotations.destructiveHint is False
                if tool.name == "ask":
                    assert annotations.readOnlyHint is False
                    assert annotations.idempotentHint is False
                    assert annotations.openWorldHint is True
                    assert "store its text in project history" in tool.description
                else:
                    assert annotations.readOnlyHint is (not telemetry)
                    assert annotations.idempotentHint is (not telemetry)
                    assert annotations.openWorldHint is False
            plan = next(tool for tool in tools if tool.name == "run_query").inputSchema
            assert "plan" in plan["properties"] and "$defs" in plan
            for name in ("goal_report", "retention_report"):
                schema = next(tool for tool in tools if tool.name == name).inputSchema
                assert {"date_from", "date_to"} <= schema["properties"].keys()
            error = await session.call_tool("run_query", {"plan": {"metric": "fake"}})
            assert error.isError


def test_shared_plan_fields_and_constraints():
    api, mcp = QueryPlan.model_json_schema(), AnalyticsPlan.model_json_schema()
    assert api["properties"].keys() == mcp["properties"].keys()
    for field in ("metric", "mode", "interval", "limit"):
        assert api["properties"][field] == mcp["properties"][field]


def test_client_filters_and_credential_scope():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = MetricairnClient(
        api_url="http://test", read_key="alr_private", management_key="alm_private"
    )
    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    plan = {
        "metric": "event_count",
        "event_name": "activation",
        "filters": [{"field": "device", "values": ["mobile"]}],
    }
    client.run_query(plan)
    client.investigate(plan)
    client.save_investigation("Mobile activation", plan)
    client.review_investigation("id", "resolved", "Fixed")
    assert [r.headers.get("X-Read-Key") for r in seen] == ["alr_private", "alr_private", None, None]
    assert [r.headers.get("X-Management-Key") for r in seen] == [
        None,
        None,
        "alm_private",
        "alm_private",
    ]
    assert b"activation" in seen[0].content
    client._http.close()


@pytest.mark.parametrize(
    "content_type, body, message",
    [
        ("text/html", "<!doctype html><html>Dashboard</html>", "non-JSON response"),
        ("application/json", '{"truncated":', "invalid JSON"),
    ],
)
def test_client_reports_proxy_and_malformed_json(content_type, body, message):
    client = MetricairnClient(api_url="http://test", read_key="alr_private")
    client._http.close()
    client._http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"Content-Type": content_type}, text=body)
        )
    )
    try:
        with pytest.raises(ValueError, match=message):
            client.goals()
    finally:
        client._http.close()


def test_conversion_and_retention_use_exact_replay_windows():
    window = {"date_from": "2026-09-01T00:00:00Z", "date_to": "2026-10-01T00:00:00Z"}
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"window": window})

    client = MetricairnClient(api_url="http://test", read_key="alr_private")
    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        client.goal_report("signup-id", 30, **window)
        client.retention(90, "activation", **window)
        assert dict(seen[0].url.params) == window
        assert dict(seen[1].url.params) == window | {"event_name": "activation"}
        with pytest.raises(ValueError, match="both date_from"):
            client.retention(90, date_from=window["date_from"])
        with pytest.raises(ValueError, match="both date_from"):
            client.goal_report("signup-id", 30, date_to=window["date_to"])
        with pytest.raises(ValueError, match="between 1 and 366"):
            _range(0)
    finally:
        client._http.close()
