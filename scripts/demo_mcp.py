"""Run the fictional Billwise examples through an actual read-only MCP session.

uv run python scripts/demo_mcp.py [--replay browser-export.json] [--output evidence.json]
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEMO_READ_KEY = "alr_bw_demo_9f2k7q4x1m8z3d6v"
ALLOWED_TOOLS = {"investigate_change", "run_query", "list_goals", "goal_report", "retention_report"}


async def run(api_url: str, replay: Path | None = None) -> dict:
    # Do not inherit write/management credentials or optional tool registrations.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("METRICAIRN_", "AGENTLENS_"))
    }
    env.update(METRICAIRN_API_URL=api_url, METRICAIRN_READ_KEY=DEMO_READ_KEY)
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "metricairn_mcp"], env=env
    )
    calls = []
    async with stdio_client(parameters) as (receive, send):
        async with ClientSession(receive, send) as session:
            await session.initialize()

            async def call(name, arguments):
                if name not in ALLOWED_TOOLS:
                    raise ValueError(f"Not a read-only Billwise example tool: {name}")
                result = await session.call_tool(name, arguments)
                content = "\n".join(item.text for item in result.content if item.type == "text")
                if result.isError:
                    raise RuntimeError(f"{name}: {content}")
                value = json.loads(content)
                calls.append({"name": name, "arguments": arguments, "result": value})
                return value

            if replay:
                examples = json.loads(replay.read_text())["calls"]
                if not isinstance(examples, list) or not 1 <= len(examples) <= 10:
                    raise ValueError("Expected an export with 1–10 example calls")
                for example in examples:
                    await call(example["name"], example["arguments"])
            else:
                end = datetime.now(timezone.utc)
                window = {
                    "date_from": (end - timedelta(days=60)).isoformat(),
                    "date_to": end.isoformat(),
                }
                await call(
                    "investigate_change",
                    {
                        "metric": "pageviews",
                        **window,
                        "date_from": (end - timedelta(days=7)).isoformat(),
                    },
                )
                await call(
                    "run_query",
                    {
                        "plan": {
                            "metric": "event_count",
                            "event_name": "signup",
                            "mode": "breakdown",
                            "dimension": "utm_campaign",
                            "limit": 10,
                            **window,
                        }
                    },
                )
                goals = await call("list_goals", {})
                signup = next((goal for goal in goals if goal["event_name"] == "signup"), None)
                if not signup:
                    raise RuntimeError("Signup goal missing. Re-run scripts/seed_billwise.py.")
                await call("goal_report", {"goal_id": signup["id"], **window})
                await call("retention_report", window)
    return {"transport": "stdio MCP", "dataset": "fictional Billwise", "calls": calls}


def error_message(error: BaseException) -> str:
    # Async MCP transports may wrap the useful tool error in a task group.
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(error_message(child) for child in error.exceptions)
    return str(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--replay", type=Path, help="Replay the exact calls in a browser evidence export"
    )
    parser.add_argument("--output", type=Path, help="Save returned JSON instead of printing it")
    args = parser.parse_args()
    try:
        evidence = asyncio.run(run(args.api_url, args.replay))
        text = json.dumps(evidence, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text)
        else:
            print(text, end="")
    except Exception as error:
        print(
            f"Billwise MCP demo failed: {error_message(error)}\nCheck the API, Billwise seed, and input/output paths, then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
