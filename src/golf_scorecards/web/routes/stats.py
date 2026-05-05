"""Stats page — quick stats + trend sparklines."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from golf_scorecards.rounds.service import RoundNotFoundError, RoundService
from golf_scorecards.rounds.stats import compute_quick_stats
from golf_scorecards.rounds.trends import compute_trends
from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import (
    get_round_service,
    get_settings_repo,
    get_templates,
)

router = APIRouter()
templates = get_templates()


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    round_service: RoundService = Depends(get_round_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> HTMLResponse:
    """Render the stats page with quick stats and trend charts."""
    summaries = await round_service.list_rounds()

    stats = None
    trends = None
    if summaries:
        stats_rounds = []
        for s in summaries[:5]:
            try:
                stats_rounds.append(await round_service.get_round(s.id))
            except RoundNotFoundError:
                continue
        if stats_rounds:
            stats = compute_quick_stats(stats_rounds)
            trends = compute_trends(stats_rounds, window=5)

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="stats.html",
            context={"stats": stats, "trends": trends},
        ),
    )
