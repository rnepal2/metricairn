"""Pydantic schemas for request/response bodies."""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------- Projects & keys ----------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = ""


class KeyPairOut(BaseModel):
    write_key: str
    read_key: str


class ProjectOut(BaseModel):
    id: str
    name: str
    domain: str
    created_at: datetime
    write_key: str | None = None  # only returned on creation
    read_key: str | None = None


# ---------- Ingest ----------
class IngestEvent(BaseModel):
    name: str = Field(min_length=1, max_length=200)  # 'pageview' or custom
    url: str = ""
    referrer: str = ""
    session_id: str = ""
    visitor_id: str = ""
    device: str = ""
    browser: str = ""
    os: str = ""
    country: str = ""
    props: dict = Field(default_factory=dict)
    revenue_amount: float = 0.0
    revenue_currency: str = ""
    at: datetime | None = None  # client timestamp; server time if omitted


class IngestBatch(BaseModel):
    events: list[IngestEvent] = Field(max_length=500)


class IngestResult(BaseModel):
    accepted: int
    rejected: int


# ---------- Query ----------
class MetricPoint(BaseModel):
    t: str  # ISO bucket start
    value: float


class BreakdownRow(BaseModel):
    value: str
    visitors: int
    pageviews: int
    revenue: float = 0.0


class OverviewOut(BaseModel):
    visitors: int
    pageviews: int
    sessions: int
    bounce_rate: float
    avg_session_seconds: float
    events: int
    revenue: float
    revenue_currency: str = "USD"


class FunnelCreate(BaseModel):
    name: str
    steps: list[dict]  # [{"kind": "page"|"event", "value": str}]


class FunnelStepReport(BaseModel):
    step: dict
    visitors: int
    conversion_from_start: float
    conversion_from_prev: float


class FunnelReportOut(BaseModel):
    funnel_id: str
    name: str
    steps: list[FunnelStepReport]
    overall_conversion: float


class AnomalyOut(BaseModel):
    date: str
    metric: str
    value: float
    expected: float
    z_score: float
    direction: str  # spike | dip


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    project_id: str | None = None  # optional; the read key's project is authoritative
    date_from: str | None = None
    date_to: str | None = None


class AskOut(BaseModel):
    answer: str
    data: list[dict] = Field(default_factory=list)
    chart: dict | None = None  # {type: 'timeseries'|'bar', x_key, y_key, title}
    sql_hint: str | None = None
    planner: str = "heuristic"  # heuristic | llm — transparency about how the question was planned


class NoteCreate(BaseModel):
    text: str
    at: datetime | None = None
