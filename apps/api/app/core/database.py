"""Database engine / session wiring. SQLite by default, Postgres via DATABASE_URL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, pool_pre_ping=True, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
    ensure_columns()


def ensure_columns() -> None:
    """Lightweight migration: create_all creates missing *tables* but never
    adds columns to existing ones. Backfill any model column absent from the
    live table with ALTER TABLE ADD COLUMN (works on SQLite and Postgres).
    New columns must be nullable (or have a server default) to backfill."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    live_tables = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in live_tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            coltype = col.type.compile(dialect=engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}"))
        # Backfill indexes declared on the model (ADD COLUMN doesn't create them).
        for idx in table.indexes:
            cols = ", ".join(c.name for c in idx.columns)
            with engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx.name} ON {table.name} ({cols})"))
