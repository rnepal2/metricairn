"""Pydantic schemas for request/response bodies."""

import json
import re
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------- Projects & keys ----------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(default="", max_length=300)


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
    management_key: str | None = None


# ---------- Ingest ----------
class IngestEvent(BaseModel):
    event_id: str | None = Field(default=None, min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)  # 'pageview' or custom
    url: str = Field(default="", max_length=2000)
    referrer: str = Field(default="", max_length=2000)
    session_id: str = Field(default="", max_length=64)
    visitor_id: str = Field(default="", max_length=64)
    user_id: str | None = Field(default=None, max_length=128)  # optional identified user
    group_id: str | None = Field(default=None, max_length=128)  # optional B2B account id
    device: str = Field(default="", max_length=30)
    browser: str = Field(default="", max_length=60)
    os: str = Field(default="", max_length=60)
    country: str = Field(default="", max_length=100)
    props: dict = Field(default_factory=dict)
    revenue_amount: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    revenue_currency: str = Field(default="", max_length=3)
    at: datetime | None = None  # client timestamp; server time if omitted

    @field_validator("props")
    @classmethod
    def bounded_props(cls, value):
        try:
            serialized = json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("props must contain finite JSON values") from None
        if len(serialized.encode()) > 8192:
            raise ValueError("props exceeds 8 KiB")
        return value

    @model_validator(mode="after")
    def validate_event(self):
        if self.at:
            self.at = (
                self.at.replace(tzinfo=timezone.utc)
                if self.at.tzinfo is None
                else self.at.astimezone(timezone.utc)
            )
            if self.at > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("event timestamp is more than five minutes in the future")
        self.revenue_currency = self.revenue_currency.upper()
        if self.name == "revenue":
            self.revenue_currency = self.revenue_currency or "USD"
            if not re.fullmatch(r"[A-Z]{3}", self.revenue_currency):
                raise ValueError("revenue currency must be a three-letter code")
        elif self.revenue_amount:
            raise ValueError("revenue_amount is only valid on revenue events")
        return self


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
    name: str = Field(min_length=1, max_length=200)
    steps: list[dict] = Field(
        min_length=2, max_length=12
    )  #  # [{"kind": "page"|"event", "value": str}]


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
    validation: dict = Field(default_factory=dict)
    sql_hint: str | None = None
    planner: str = "heuristic"  # heuristic | llm — transparency about how the question was planned
    coverage_notes: list[str] = Field(default_factory=list)  # what the answer couldn't see
    based_on: dict = Field(
        default_factory=dict
    )  # {events, event_names, date_range} — what backed the answer


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    at: datetime | None = None


# ---------- Alert delivery ----------
class AlertChannelCreate(BaseModel):
    kind: str = Field(pattern="^(email|slack)$")  # 'email' -> address, 'slack' -> webhook URL
    target: str = Field(min_length=3, max_length=500)


class AlertChannelOut(BaseModel):
    id: str
    kind: str
    target: str
    enabled: bool
    created_at: datetime


class AlertRuleCreate(BaseModel):
    name: str = ""
    metric: str = Field(default="any", pattern="^(revenue|pageviews|any)$")
    direction: str = Field(default="any", pattern="^(dip|spike|any)$")
    min_z: float = Field(default=2.5, ge=1.0, le=10.0)
    cooldown_hours: float = Field(default=24.0, ge=1.0, le=720.0)


class AlertRuleOut(BaseModel):
    id: str
    name: str
    metric: str
    direction: str
    min_z: float
    cooldown_hours: float
    enabled: bool
    created_at: datetime


class AlertDeliveryOut(BaseModel):
    id: str
    channel_id: str
    rule_id: str
    anomaly_key: str
    status: str
    detail: str
    created_at: datetime
