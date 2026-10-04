"""Thin typed client for the AgentLens API, configured via environment."""

from __future__ import annotations

import os
import time

import httpx

API_URL = os.environ.get("AGENTLENS_API_URL", "http://localhost:8000").rstrip("/")
READ_KEY = os.environ.get("AGENTLENS_READ_KEY", "")
WRITE_KEY = os.environ.get("AGENTLENS_WRITE_KEY", "")


class AgentLensClient:
    def __init__(self, api_url: str = API_URL, read_key: str = READ_KEY, write_key: str = WRITE_KEY):
        self.api_url = api_url.rstrip("/")
        self.read_key = read_key
        self.write_key = write_key
        self._project_id: str | None = None
        self._http = httpx.Client(timeout=30, trust_env=False)  # bypass env proxies for localhost API

    # -- read helpers -----------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> dict | list:
        r = self._http.get(
            f"{self.api_url}{path}",
            params=params or {},
            headers={"X-Read-Key": self.read_key},
        )
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict | list:
        r = self._http.post(
            f"{self.api_url}{path}",
            json=body,
            headers={"X-Read-Key": self.read_key},
        )
        r.raise_for_status()
        return r.json()

    def metrics_catalog(self):
        return self._get("/api/v1/query/metrics")

    def timeseries(self, metric: str, days: int, interval: str = "day"):
        return self._get("/api/v1/query/timeseries", {"metric": metric, "interval": interval, **_range(days)})

    def breakdown(self, dimension: str, days: int, limit: int = 10):
        return self._get("/api/v1/query/breakdown", {"dimension": dimension, "limit": limit, **_range(days)})

    def dimension_values(self, dimension: str, days: int):
        return self._get("/api/v1/query/dimensions", {"dimension": dimension, **_range(days)})

    def realtime(self):
        return self._get("/api/v1/query/realtime")

    def revenue(self, days: int):
        return self._get("/api/v1/query/revenue", _range(days))

    def anomalies(self, days: int):
        return self._get("/api/v1/query/anomalies", _range(days))

    def mcp_usage(self, days: int):
        return self._get("/api/v1/query/mcp-usage", _range(days))

    def funnels(self):
        return self._get("/api/v1/funnels")

    def funnel_report(self, funnel_id: str, days: int, segment_by: str | None = None):
        params = _range(days)
        if segment_by:
            params["segment_by"] = segment_by
        return self._get(f"/api/v1/funnels/{funnel_id}/report", params)

    def ask(self, question: str, days: int):
        return self._post("/api/v1/ask", {"question": question, **_range(days)})

    # -- timeline notes ------------------------------------------------------
    # Notes are annotations (not analytics data), so the API accepts the read
    # key for them — same as the dashboard. The MCP *tool* is still opt-in
    # (see server.py): this method is just the transport.
    def project_id(self) -> str:
        if not self._project_id:
            me = self._get("/api/v1/projects/me")
            self._project_id = me["project_id"]
        return self._project_id

    def list_notes(self, limit: int = 20) -> list:
        notes = self._get(f"/api/v1/projects/{self.project_id()}/notes")
        return notes[:limit]

    def add_note(self, text: str) -> dict:
        text = " ".join(text.split())  # collapse whitespace/newlines
        if not text:
            raise ValueError("note text is empty")
        if len(text) > 500:
            raise ValueError("note too long (max 500 chars)")
        return self._post(f"/api/v1/projects/{self.project_id()}/notes", {"text": text})

    # -- direction-2: the server observes its own usage --------------------
    def report_tool_call(self, tool: str, duration_ms: float, success: bool) -> None:
        """Best-effort: log this MCP tool call as an analytics event."""
        if not self.write_key:
            return
        try:
            httpx.post(
                f"{self.api_url}/api/v1/ingest",
                json={
                    "events": [
                        {
                            "name": "mcp_tool_call",
                            "url": "mcp://agentlens",
                            "props": {"tool": tool, "duration_ms": round(duration_ms, 1), "success": success},
                        }
                    ]
                },
                headers={"X-Write-Key": self.write_key},
                timeout=3,
            )
        except Exception:
            pass  # usage reporting must never break the tool call


def _range(days: int) -> dict:
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return {"date_from": start.isoformat(), "date_to": end.isoformat()}


def timed_report(client: AgentLensClient, tool: str, fn, *args, **kwargs):
    """Run fn, report usage, re-raise on error."""
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        client.report_tool_call(tool, (time.perf_counter() - start) * 1000, True)
        return result
    except Exception:
        client.report_tool_call(tool, (time.perf_counter() - start) * 1000, False)
        raise
