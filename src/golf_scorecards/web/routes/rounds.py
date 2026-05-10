"""Rounds routes — browse the round history and see round details.

The "Rounds" tab. Read-only listing + detail. Editing happens through
``play.py``.
"""

from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.rounds.match import compute_match_result
from golf_scorecards.rounds.service import RoundNotFoundError, RoundService
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_insights_service,
    get_round_service,
    get_templates,
)
from golf_scorecards.web.routes._helpers import (
    stableford_map,
    strokes_received_map,
    total_stableford,
)

router = APIRouter()
templates = get_templates()


@router.get("/rounds", response_class=HTMLResponse)
async def round_list(
    request: Request,
    course: str | None = None,
    round_service: RoundService = Depends(get_round_service),
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> HTMLResponse:
    """Render the round history list with optional course filter."""
    user_id = request.state.user.id
    course_slug = course if course else None
    summaries = await round_service.list_rounds(user_id, course_slug=course_slug)

    round_stableford: dict[str, int] = {}
    match_results: dict[str, str] = {}
    for s in summaries:
        try:
            r = await round_service.get_round(s.id, user_id)
            if s.scoring_mode == "match_play":
                mr = compute_match_result(r.holes)
                match_results[s.id] = mr.result_text
            else:
                pts = total_stableford(r)
                if pts is not None:
                    round_stableford[r.id] = pts
        except RoundNotFoundError:
            continue

    course_options = catalog_service.list_course_options()

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_list.html",
            context={
                "rounds": summaries,
                "round_stableford": round_stableford,
                "match_results": match_results,
                "course_options": course_options,
                "selected_course": course_slug or "",
            },
        ),
    )


@router.get("/rounds/{round_id}", response_class=HTMLResponse)
async def round_detail(
    request: Request,
    round_id: str,
    round_service: RoundService = Depends(get_round_service),
    insights_service: InsightsService | None = Depends(get_insights_service),
) -> HTMLResponse:
    """Render the read-only detail view for a saved round."""
    try:
        r = await round_service.get_round(round_id, request.state.user.id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    snapshot = json.loads(r.course_snapshot)
    played = {h.hole_number for h in r.holes}
    strokes = strokes_received_map(snapshot["holes"], r.playing_handicap, played)
    stableford = stableford_map(r.holes, strokes)

    scored_holes = [h for h in r.holes if h.score is not None]
    total_score: int | None = sum(
        cast(int, h.score) for h in scored_holes
    ) if scored_holes else None
    total_putts = sum(h.putts for h in scored_holes if h.putts is not None)
    total_par = sum(h.par for h in scored_holes)
    total_pts = (
        sum(v for v in stableford.values() if v is not None)
        if scored_holes
        else None
    )

    stats = {
        "total_score": total_score,
        "total_par": total_par,
        "score_vs_par": (total_score - total_par) if total_score is not None else None,
        "total_putts": total_putts,
        "total_stableford": total_pts,
    }

    cached_insights: list[str] | None = None
    if insights_service is not None:
        cached_insights = await insights_service.get_cached_insights(
            cache_key=f"round:{round_id}",
        )

    match_result = (
        compute_match_result(r.holes)
        if r.scoring_mode == "match_play" else None
    )

    # Scramble context
    scramble_tags: list[dict[str, str]] = []
    drive_counts: dict[str, int] = {}
    if r.scoring_mode == "scramble":
        from golf_scorecards.web.routes.play import _scramble_tags
        scramble_tags = _scramble_tags(r.teammates)
        for h in r.holes:
            if h.drive_used:
                drive_counts[h.drive_used] = drive_counts.get(h.drive_used, 0) + 1

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_detail.html",
            context={
                "round": r,
                "snapshot": snapshot,
                "stats": stats,
                "strokes_map": strokes,
                "stableford": stableford,
                "round_insights": cached_insights,
                "insights_enabled": insights_service is not None,
                "match_result": match_result,
                "scramble_tags": scramble_tags,
                "drive_counts": drive_counts,
            },
        ),
    )


@router.post("/rounds/{round_id}/delete")
async def round_delete(
    request: Request,
    round_id: str,
    round_service: RoundService = Depends(get_round_service),
) -> RedirectResponse:
    """Delete a round and redirect back.

    Redirects to the URL given by the ``next`` query parameter if present
    and in the allow-list, otherwise falls back to ``GET /rounds``.
    """
    try:
        await round_service.delete_round(round_id, request.state.user.id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    next_url = request.query_params.get("next", "/rounds")
    allowed = {"/", "/rounds"}
    redirect = next_url if next_url in allowed else "/rounds"
    return RedirectResponse(url=redirect, status_code=303)
