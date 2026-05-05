"""Settings routes — handicap index, etc."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import get_settings_repo, get_templates

router = APIRouter()
templates = get_templates()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> HTMLResponse:
    """Render the settings page."""
    handicap_index = await settings_repo.get("handicap_index")
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="settings_page.html",
            context={"handicap_index": handicap_index},
        ),
    )


@router.post("/settings/handicap")
async def update_handicap_index(
    handicap_index: str = Form(default=""),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Update the player's stored handicap index."""
    value = handicap_index.strip()
    if value:
        await settings_repo.set("handicap_index", value)
    return RedirectResponse(url="/settings", status_code=303)
