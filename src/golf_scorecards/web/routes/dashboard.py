"""Dashboard route — the landing page at ``/``."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.rounds.service import RoundService
from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_insights_service,
    get_round_service,
    get_settings_repo,
    get_templates,
)
from golf_scorecards.web.routes._helpers import build_home_context

router = APIRouter()
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
    round_service: RoundService = Depends(get_round_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    insights_service: InsightsService | None = Depends(get_insights_service),
) -> HTMLResponse:
    """Render the landing page with action cards, quick stats, and recent rounds."""
    context = await build_home_context(
        catalog_service, round_service, settings_repo, insights_service,
    )
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request, name="home.html", context=context,
        ),
    )
