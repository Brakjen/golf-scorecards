"""FastAPI application factory and ASGI entry point."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from golf_scorecards.config import get_settings
from golf_scorecards.db.connection import init_db_sync
from golf_scorecards.web.auth import install_auth
from golf_scorecards.web.dependencies import get_catalog_service, get_static_directory, get_templates
from golf_scorecards.web.routes import router as web_router

# Cache-bust token: generated once at process start (i.e. on each deploy)
_ASSET_VERSION = str(int(time.time()))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Pre-load the course catalog and initialise the database on startup."""
    get_catalog_service()
    settings = get_settings()
    init_db_sync(settings.db_path)

    # In DEV mode, seed the database with dummy data if it's empty
    if settings.app_env == "development":
        import sqlite3

        conn = sqlite3.connect(settings.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
        finally:
            conn.close()
        if count == 0:
            from golf_scorecards.dev_seed import seed_database
            seed_database(settings.db_path)

    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=get_static_directory()), name="static")
    app.include_router(web_router)
    install_auth(app)

    # Make asset version available to all templates for cache-busting
    templates = get_templates()
    templates.env.globals["_v"] = _ASSET_VERSION

    @app.get("/health", tags=["system"])
    def healthcheck() -> dict[str, str]:
        """Return application health status."""
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
