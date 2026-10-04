"""Application configuration — everything via environment, sane local defaults."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AgentLens API"
    # SQLite by default for zero-setup demo; set DATABASE_URL for Postgres.
    database_url: str = "sqlite:///./data/agentlens.db"
    # Optional LLM keys for the natural-language `ask` endpoint / MCP ask tool.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ask_model: str = "claude-haiku-4-5"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Alert delivery: email goes through Resend; Slack needs only a webhook URL.
    resend_api_key: str = ""
    alerts_from_email: str = "AgentLens <alerts@agentlens.dev>"
    # In-process scheduler runs the alert check every N minutes. Disable when
    # running multiple API workers (run one scheduler instead).
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 30
    # Optional Stripe webhook receiver: when set, POST /api/v1/integrations/stripe/webhook
    # verifies Stripe signatures and turns checkout.session.completed / invoice.paid
    # into `revenue` events. Off by default — the push model means the customer
    # holds the tap.
    stripe_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
