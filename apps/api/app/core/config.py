"""Application configuration — everything via environment, sane local defaults."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Metricairn API"
    provisioning_token: str = ""  # Set before exposing project creation publicly.
    # SQLite by default for zero-setup demo; set DATABASE_URL for Postgres.
    database_url: str = Field(
        default_factory=lambda: (
            "sqlite:///./data/agentlens.db"
            if Path("data/agentlens.db").exists() and not Path("data/metricairn.db").exists()
            else "sqlite:///./data/metricairn.db"
        )
    )
    # Optional SQL generation. Auto preserves legacy key selection; no failover.
    llm_provider: Literal[
        "auto", "disabled", "openai", "anthropic", "google", "openai_compatible"
    ] = "auto"
    llm_model: str = ""
    llm_api: Literal["chat_completions", "responses"] = "chat_completions"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_timeout_s: float = Field(default=12, ge=1, le=20)
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=16384)
    llm_reasoning_effort: Literal["", "minimal", "low", "medium", "high", "xhigh"] = ""
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    ask_model: str = "claude-haiku-4-5"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Alert delivery: email goes through Resend; Slack needs only a webhook URL.
    resend_api_key: str = ""
    alerts_from_email: str = "Metricairn <alerts@example.com>"
    # In-process scheduler runs the alert check every N minutes. Disable when
    # running multiple API workers (run one scheduler instead).
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = Field(default=30, ge=1, le=1440)
    # Optional Stripe webhook receiver: when set, POST /api/v1/integrations/stripe/webhook
    # verifies Stripe signatures and turns checkout.session.completed / invoice.paid
    # into `revenue` events. Off by default — the push model means the customer
    # holds the tap.
    stripe_webhook_secret: str = ""
    # Agentic SQL analytics: the LLM writes SQL against the fixed event schema.
    # Requires a configured provider; without one, ask stays deterministic.
    agentic_sql_enabled: bool = True
    agentic_sql_timeout_s: int = Field(default=15, ge=1, le=60)
    agentic_sql_row_cap: int = Field(default=200, ge=1, le=10000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
