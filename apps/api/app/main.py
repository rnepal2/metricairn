"""Metricairn API — privacy-friendly product analytics your AI agent can query."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.core.config import get_settings
from app.core.database import init_db
from app.core.http import RequestGuard
from app.routers import (
    alerts,
    ask,
    digest,
    exploration,
    funnels,
    ingest,
    integrations,
    keys,
    privacy,
    projects,
    query,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    scheduler = None
    # PYTEST_CURRENT_TEST is set by pytest automatically — never spawn
    # background threads inside the test suite.
    if settings.scheduler_enabled and not os.environ.get("PYTEST_CURRENT_TEST"):
        from apscheduler.schedulers.background import BackgroundScheduler

        from app.services.alerting import check_all_projects
        from app.services.digest import check_digests

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            check_all_projects,
            "interval",
            minutes=settings.scheduler_interval_minutes,
            id="alert_check",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            check_digests,
            "interval",
            minutes=settings.scheduler_interval_minutes,
            id="digest_check",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
    try:
        yield
    finally:
        from app.services.llm import close_clients

        close_clients()
        if scheduler:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestGuard)

    @app.exception_handler(ValueError)
    async def invalid_query(request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    for r in (
        projects.router,
        keys.router,
        ingest.router,
        query.router,
        exploration.router,
        funnels.router,
        ask.router,
        alerts.router,
        digest.router,
        integrations.router,
        privacy.router,
    ):
        app.include_router(r)

    # Serve the built tracker snippet so the Settings page snippet URL works out of the box.
    tracker_dist = Path(
        os.environ.get(
            "TRACKER_DIST",
            str(Path(__file__).resolve().parents[3] / "packages" / "tracker" / "dist"),
        )
    )
    if tracker_dist.is_dir():
        app.mount("/static", StaticFiles(directory=str(tracker_dist)), name="static")

    @app.get("/health")
    def health():
        return {"ok": True, "service": "metricairn-api", "version": __version__}

    @app.get("/ready")
    def ready():
        from sqlalchemy import text

        from app.core.database import engine

        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"ok": True}
        except Exception:
            return JSONResponse(status_code=503, content={"ok": False})

    web_dist = Path(
        os.environ.get("WEB_DIST", str(Path(__file__).resolve().parents[2] / "web" / "dist"))
    )
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="dashboard")
    return app


app = create_app()
