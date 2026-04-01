"""FastAPI application with APScheduler heartbeat and full lifecycle management.

Security: CORS restricted, security headers, static file serving.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import load_settings
from app.cycle_engine import CycleEngine
from app.llm_client import LLMClient
from app.memory.chromadb_store import ChromaDBStore
from app.storage.sqlite_store import SQLiteStore
from app.tools.search_factory import create_search_provider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init storage, scheduler, cycle engine."""
    settings = load_settings()
    app.state.settings = settings

    # Init storage
    data_dir = Path(settings.storage.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    sqlite = SQLiteStore(settings.storage.sqlite_path)
    await sqlite.init()
    app.state.sqlite = sqlite

    chromadb = ChromaDBStore(settings.storage.chromadb_dir)
    chromadb.connect()
    app.state.chromadb = chromadb

    # Init cycle engine (only if API keys available)
    missing = settings.validate_api_keys()
    if not missing:
        llm = LLMClient(
            api_key=settings.openrouter_api_key,
            model=settings.model,
        )
        search = create_search_provider(
            provider_name=settings.search_provider,
            api_key=settings.get_search_api_key(),
        )

        engine = CycleEngine(
            settings=settings,
            llm=llm,
            chromadb=chromadb,
            sqlite=sqlite,
            data_dir=data_dir,
            search=search,
        )
        app.state.cycle_engine = engine

        # APScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            engine.run_cycle,
            "interval",
            seconds=settings.heartbeat_interval,
            id="heartbeat",
            name="AI Cycle Heartbeat",
        )
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info(
            "Scheduler started: heartbeat every %ds, model=%s",
            settings.heartbeat_interval,
            settings.model,
        )
    else:
        logger.warning("Missing API keys: %s — scheduler disabled", missing)
        app.state.cycle_engine = None
        app.state.scheduler = None

    # Static files for assets
    rooms_dir = data_dir / "rooms"
    rooms_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(rooms_dir)), name="assets")

    yield

    # Shutdown
    if getattr(app.state, "scheduler", None):
        app.state.scheduler.shutdown(wait=False)
    if getattr(app.state, "sqlite", None):
        await app.state.sqlite.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="The Life",
        description="Autonomous AI entity exploring existence",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    settings = load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    # Routes
    app.include_router(router)

    return app


app = create_app()
