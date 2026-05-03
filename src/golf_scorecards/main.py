"""FastAPI application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from golf_scorecards.config import get_settings
from golf_scorecards.db.connection import init_db_sync
from golf_scorecards.web.auth import install_auth
from golf_scorecards.web.dependencies import get_catalog_service, get_static_directory
from golf_scorecards.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Pre-load the course catalog and initialise the database on startup."""
    get_catalog_service()
    settings = get_settings()
    init_db_sync(settings.db_path)
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=get_static_directory()), name="static")
    app.include_router(web_router)
    install_auth(app)

    @app.get("/health", tags=["system"])
    def healthcheck() -> dict[str, str]:
        """Return application health status."""
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
