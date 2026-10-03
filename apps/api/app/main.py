"""AgentLens API — privacy-friendly product analytics your AI agent can query."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import init_db
from app.routers import ask, funnels, ingest, projects, query


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (projects.router, ingest.router, query.router, funnels.router, ask.router):
        app.include_router(r)

    # Serve the built tracker snippet so the Settings page snippet URL works out of the box.
    tracker_dist = Path(__file__).resolve().parents[3] / "packages" / "tracker" / "dist"
    if tracker_dist.is_dir():
        app.mount("/static", StaticFiles(directory=str(tracker_dist)), name="static")

    @app.get("/health")
    def health():
        return {"ok": True, "service": "agentlens-api", "version": "0.1.0"}

    return app


app = create_app()
