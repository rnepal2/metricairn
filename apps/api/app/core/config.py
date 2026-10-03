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


@lru_cache
def get_settings() -> Settings:
    return Settings()
