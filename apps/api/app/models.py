"""SQLAlchemy models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    keys: Mapped[list["ApiKey"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    funnels: Mapped[list["Funnel"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(200), default="")
    scopes: Mapped[str] = mapped_column(String(50), default="read")  # csv: read,write
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped[Project] = relationship(back_populates="keys")


class Event(Base):
    """One tracked hit. name is 'pageview' for page views, otherwise a custom event name.
    Revenue is recorded as an event named 'revenue' with revenue_amount set."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    visitor_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    name: Mapped[str] = mapped_column(String(200), index=True)
    path: Mapped[str] = mapped_column(String(1000), default="")
    url: Mapped[str] = mapped_column(String(2000), default="")
    referrer: Mapped[str] = mapped_column(String(2000), default="")
    utm_source: Mapped[str] = mapped_column(String(300), default="")
    utm_medium: Mapped[str] = mapped_column(String(300), default="")
    utm_campaign: Mapped[str] = mapped_column(String(300), default="")
    device: Mapped[str] = mapped_column(String(30), default="")
    browser: Mapped[str] = mapped_column(String(60), default="")
    os: Mapped[str] = mapped_column(String(60), default="")
    country: Mapped[str] = mapped_column(String(100), default="")
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    revenue_amount: Mapped[float] = mapped_column(default=0.0)
    revenue_currency: Mapped[str] = mapped_column(String(10), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    project: Mapped[Project] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_events_project_created", "project_id", "created_at"),
        Index("ix_events_project_name", "project_id", "name"),
    )


class Funnel(Base):
    __tablename__ = "funnels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # steps: [{"kind": "page"|"event", "value": "/pricing" | "signup"}]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped[Project] = relationship(back_populates="funnels")


class Note(Base):
    """Founder annotations on the timeline (launches, campaigns) — shown on charts."""

    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AlertChannel(Base):
    """Where anomaly alerts go: email address or Slack webhook. Managed by the
    founder with a write key; the scheduler delivers to every enabled channel."""

    __tablename__ = "alert_channels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # 'email' | 'slack'
    target: Mapped[str] = mapped_column(String(500))  # address or webhook URL
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AlertRule(Base):
    """Which anomalies trigger a notification. If a project has channels but no
    enabled rules, a built-in default (any metric/direction, |z| >= 3, 24h
    cooldown) applies."""

    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    metric: Mapped[str] = mapped_column(String(20), default="any")  # 'revenue'|'pageviews'|'any'
    direction: Mapped[str] = mapped_column(String(20), default="any")  # 'dip'|'spike'|'any'
    min_z: Mapped[float] = mapped_column(default=2.5)
    cooldown_hours: Mapped[float] = mapped_column(default=24.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AlertDelivery(Base):
    """Log of every alert decision — sent, failed, or skipped. Doubles as the
    cooldown ledger and the dashboard's delivery history."""

    __tablename__ = "alert_deliveries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[str] = mapped_column(String(32), default="")
    rule_id: Mapped[str] = mapped_column(String(32), default="")
    anomaly_key: Mapped[str] = mapped_column(String(200), index=True)  # metric:direction:date[:date_end]
    status: Mapped[str] = mapped_column(String(20))  # 'sent'|'failed'|'skipped'
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
