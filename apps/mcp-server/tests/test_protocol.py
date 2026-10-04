"""Real stdio MCP handshake and public tool contract."""

import os
import sys

import httpx
import pytest
from app.services.exploration import QueryPlan
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from metricairn_mcp.client import MetricairnClient
from metricairn_mcp.schemas import AnalyticsPlan


@pytest.mark.asyncio
async def test_stdio_handshake_and_read_only_tool_schemas():
    env = dict(
        os.environ, METRICAIRN_ENABLE_NOTE_WRITE="0", METRICAIRN_ENABLE_INVESTIGATION_WRITE="0"
    )
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", "metricairn_mcp"], env=env)
    ) as (receive, send):
        async with ClientSession(receive, send) as session:
            info = await session.initialize()
            assert info.serverInfo.name == "metricairn"
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
            assert all(tool.annotations.readOnlyHint for tool in tools)
            plan = next(tool for tool in tools if tool.name == "run_query").inputSchema
            assert "plan" in plan["properties"] and "$defs" in plan
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
