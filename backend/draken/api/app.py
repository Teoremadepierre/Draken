"""FastAPI application factory.

The API and the dashboard are served by the same process: one command, one port,
no build step. That is deliberate - it means deploying Draken on your own VPS is
copying a directory and running one service.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from draken import __version__
from draken.api.routes import (
    audits,
    auth,
    backlinks,
    geo,
    jobs,
    keywords,
    opportunities,
    outreach,
    projects,
)
from draken.core.config import FRONTEND_DIR, settings
from draken.core.database import init_db, session_scope
from draken.core.logging import get_logger, setup_logging
from draken.engines.geo import engines as ai_engines
from draken.engines.scheduler import handlers as _handlers  # noqa: F401 - registers job kinds
from draken.engines.scheduler import jobs as job_runner
from draken.engines.serp import fetcher

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    log.info("Draken %s starting (env=%s, db=%s)", __version__, settings.env,
             settings.database_url.split("://")[0])

    # Load the link source catalog on first boot so the tool is useful immediately.
    try:
        from sqlalchemy import select

        from draken.core.models import LinkSource
        from draken.services.opportunities import sync_catalog

        with session_scope() as db:
            if not db.execute(select(LinkSource.id).limit(1)).first():
                result = sync_catalog(db)
                log.info("seeded link source catalog: %s sources", result["total"])
    except Exception as exc:  # noqa: BLE001 - never block startup on seeding
        log.warning("could not seed link source catalog: %s", exc)

    if settings.scheduler_enabled:
        try:
            resumed = await job_runner.resume_pending()
            if resumed:
                log.info("resumed %d pending job(s)", resumed)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not resume pending jobs: %s", exc)

    yield
    log.info("Draken shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Draken SEO Suite",
        version=__version__,
        description=(
            "Self-hosted SEO intelligence, backlink acquisition and AI-visibility platform. "
            "Keyword research, site audit, rank tracking, backlink analysis, a 355-source link "
            "opportunity engine, submission and outreach pipelines, and generative-engine "
            "visibility tracking."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        auth.router,
        projects.router,
        keywords.router,
        audits.router,
        backlinks.router,
        opportunities.router,
        outreach.router,
        geo.router,
        jobs.router,
    ):
        app.include_router(router)

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "env": settings.env,
            "auth_enabled": settings.auth_enabled,
            "serp_provider": fetcher.active_provider(),
            "serp_approximate": fetcher.active_provider() not in {"serpapi", "dataforseo"},
            "ai_engines": ai_engines.available_engines(),
            "submissions": {
                "dry_run": settings.submissions_dry_run,
                "require_approval": settings.submissions_require_approval,
            },
            "outreach_send_enabled": settings.outreach_send_enabled,
            "job_kinds": job_runner.registered_kinds(),
        }

    @app.get("/api/config")
    def client_config() -> dict:
        """What the dashboard needs to know about this deployment."""
        return {
            "version": __version__,
            "auth_enabled": settings.auth_enabled,
            "serp_provider": fetcher.active_provider(),
            "serp_approximate": fetcher.active_provider() not in {"serpapi", "dataforseo"},
            "ai_engines_configured": settings.ai_engines_configured(),
            "submissions_dry_run": settings.submissions_dry_run,
            "submissions_require_approval": settings.submissions_require_approval,
            "outreach_send_enabled": settings.outreach_send_enabled,
            "suggest_providers": settings.suggest_provider_list,
        }

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    # --- dashboard -------------------------------------------------------
    if FRONTEND_DIR.exists():
        app.mount(
            "/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static"
        )

        @app.get("/", include_in_schema=False)
        def dashboard() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon() -> FileResponse:
            icon = FRONTEND_DIR / "assets" / "favicon.svg"
            return FileResponse(str(icon)) if icon.exists() else FileResponse(
                str(FRONTEND_DIR / "index.html")
            )
    else:
        log.warning("frontend directory not found at %s; API only", FRONTEND_DIR)

    return app


app = create_app()
