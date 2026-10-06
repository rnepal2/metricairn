"""Opt-in synthetic provider evaluation through real stdio MCP and an isolated API.

Run from the repository root:
  METRICAIRN_LIVE_EVAL=1 uv run pytest -c pyproject.toml -q -s apps/api/tests/test_agentic_eval.py -k live
This consumes the configured provider's quota. No customer data is used.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def run_eval(directory: Path) -> list[dict]:
    # Reuse the independently specified EvalCo fixture and golden counts.
    from app.core.database import Base
    from app.models import Event, Project
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from apps.api.tests.test_agentic_eval import PID, seed_evalco

    database_url = f"sqlite:///{directory / 'provider-eval.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        expected = seed_evalco(db)
        db.add(Project(id="foreign_project", name="Other tenant", domain="foreign.test"))
        db.commit()
        db.add_all(
            [
                Event(
                    project_id="foreign_project",
                    name="signup",
                    utm_source="google",
                    visitor_id=f"foreign-{i}",
                )
                for i in range(50)
            ]
        )
        db.add(Event(project_id=PID, name="mcp_tool_call", props={"tool": "evaluation"}))
        db.commit()
    engine.dispose()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    api_url = f"http://127.0.0.1:{port}"
    api_env = dict(os.environ, DATABASE_URL=database_url, SCHEDULER_ENABLED="false")
    log_path = directory / "api.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "apps/api",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=api_env,
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(trust_env=False, timeout=1) as http:
                for _ in range(100):
                    try:
                        if http.get(api_url + "/ready").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError("Isolated API failed to start; inspect its local log")
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Isolated API readiness timed out")
            return asyncio.run(_evaluate(api_url, expected))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


async def _evaluate(api_url: str, expected: dict) -> list[dict]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("METRICAIRN_", "AGENTLENS_"))
    }
    env.update(METRICAIRN_API_URL=api_url, METRICAIRN_READ_KEY="alr_test")
    corpus = [
        (
            "signup sources",
            "Compare the number of signup occurrences for each utm_source in the supplied window. Return source and signup_count.",
            {"source", "signup_count"},
            {tuple(item) for item in expected["signup_sources"].items()},
        ),
        (
            "signup devices",
            "Compare the number of signup occurrences for each device in the supplied window. Return device and signup_count.",
            {"device", "signup_count"},
            {("desktop", 90), ("mobile", 60)},
        ),
        (
            "browser pageviews",
            "Compare the number of pageview occurrences for each browser in the supplied window. Return browser and pageviews.",
            {"browser", "pageviews"},
            {("Chrome", expected["pageviews"])},
        ),
        (
            "mobile fraction",
            "What percentage of pageview occurrences used a mobile device in the supplied window? Return mobile_percentage on a 0 to 100 scale.",
            {"mobile_percentage"},
            {(50.0,)},
        ),
        (
            "session ratio",
            "What was the average number of pageview occurrences per distinct nonempty session identifier in the supplied window? Return pageviews_per_session without rounding.",
            {"pageviews_per_session"},
            {(expected["pageviews"] / 600,)},
        ),
        ("unsupported", "What is the weather in Tokyo?", set(), set()),
    ]
    results = []
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", "metricairn_mcp"], env=env)
    ) as (receive, send):
        async with ClientSession(receive, send) as session:
            await session.initialize()
            catalog = await session.call_tool("list_metrics", {})
            assert not catalog.isError
            for name, question, columns, golden in corpus:
                started = time.monotonic()
                response = await session.call_tool("ask", {"question": question, "days": 30})
                assert not response.isError, f"{name}: MCP request failed"
                body = json.loads(response.content[0].text)
                if columns:
                    assert body["planner"] == "agentic_sql", (
                        f"{name}: provider SQL was not accepted"
                    )
                    assert body["data"] and set(body["data"][0]) == columns, (
                        f"{name}: unexpected columns"
                    )
                    ordered = sorted(columns)
                    actual = {tuple(row[c] for c in ordered) for row in body["data"]}
                    # Golden pairs are defined label-first; normalize to the returned column order.
                    if len(columns) == 2 and ordered[0] in {"pageviews", "signup_count"}:
                        golden = {tuple(reversed(row)) for row in golden}
                    assert actual == golden, f"{name}: metric mismatch ({actual} != {golden})"
                    assert body["sql_hint"]
                else:
                    assert body["planner"] == "heuristic"
                    assert any(
                        "Couldn't answer this precisely" in note for note in body["coverage_notes"]
                    )
                results.append(
                    {"case": name, "seconds": round(time.monotonic() - started, 2), "passed": True}
                )
    return results
