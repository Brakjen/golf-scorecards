"""Settings routes — handicap index, etc."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse

from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import get_settings_repo

router = APIRouter()


@router.post("/settings/handicap")
async def update_handicap_index(
    handicap_index: str = Form(default=""),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Update the player's stored handicap index."""
    value = handicap_index.strip()
    if value:
        await settings_repo.set("handicap_index", value)
    return RedirectResponse(url="/", status_code=303)
