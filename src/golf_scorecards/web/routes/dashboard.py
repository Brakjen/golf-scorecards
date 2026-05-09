"""Dashboard route — the Play page at ``/``."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_settings_repo,
    get_templates,
)

router = APIRouter()
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> HTMLResponse:
    """Render the Play page with the Enter Round form."""
    course_options = catalog_service.list_course_options()
    initial_course = course_options[0]
    hci_raw = await settings_repo.get("handicap_index", request.state.user.id)
    context = {
        "course_options": course_options,
        "initial_course_slug": initial_course["course_slug"],
        "initial_tee_name": initial_course["tees"][0]["name"],
        "handicap_index": hci_raw,
    }
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request, name="home.html", context=context,
        ),
    )
