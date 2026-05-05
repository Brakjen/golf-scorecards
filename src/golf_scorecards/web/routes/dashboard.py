"""Dashboard route — the Play page at ``/``."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_templates,
)

router = APIRouter()
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> HTMLResponse:
    """Render the Play page with the Enter Round form."""
    course_options = catalog_service.list_course_options()
    initial_course = course_options[0]
    context = {
        "course_options": course_options,
        "initial_course_slug": initial_course["course_slug"],
        "initial_tee_name": initial_course["tees"][0],
    }
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request, name="home.html", context=context,
        ),
    )
