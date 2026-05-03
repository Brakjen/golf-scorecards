"""Coach routes — LLM-powered insights and free-form Q&A."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.rounds.service import RoundNotFoundError, RoundService
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


@router.post("/insights/refresh")
async def insights_refresh(
    round_service: RoundService = Depends(get_round_service),
    insights_service: InsightsService | None = Depends(get_insights_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Generate fresh coaching insights from the last 5 rounds."""
    if insights_service is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key not configured",
        )

    summaries = await round_service.list_rounds()
    if not summaries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rounds recorded yet",
        )

    rounds = []
    for s in summaries[:5]:
        try:
            rounds.append(await round_service.get_round(s.id))
        except RoundNotFoundError:
            continue

    if not rounds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rounds with data found",
        )

    await insights_service.generate_insights(
        rounds,
        handicap_index=await settings_repo.get("handicap_index"),
        force=True,
    )
    return RedirectResponse(url="/", status_code=303)


@router.post("/rounds/{round_id}/insights/refresh")
async def round_insights_refresh(
    round_id: str,
    round_service: RoundService = Depends(get_round_service),
    insights_service: InsightsService | None = Depends(get_insights_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Generate fresh coaching insights focused on a single round."""
    if insights_service is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key not configured",
        )

    try:
        r = await round_service.get_round(round_id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    await insights_service.generate_insights(
        [r],
        handicap_index=await settings_repo.get("handicap_index"),
        force=True,
        cache_key=f"round:{round_id}",
    )
    return RedirectResponse(url=f"/rounds/{round_id}", status_code=303)


@router.post("/ask", response_class=HTMLResponse, response_model=None)
async def ask_dashboard(
    request: Request,
    question: str = Form(default=""),
    catalog_service: CatalogService = Depends(get_catalog_service),
    round_service: RoundService = Depends(get_round_service),
    insights_service: InsightsService | None = Depends(get_insights_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> HTMLResponse | RedirectResponse:
    """Send a free-form coaching question to the LLM with full round context.

    Renders the dashboard with the answer attached. The answer is not
    persisted across page loads (a refresh of ``/`` clears it) so the
    user gets a clean slate every time.
    """
    if insights_service is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key not configured",
        )

    question_clean = question.strip()
    if not question_clean:
        return RedirectResponse(url="/", status_code=303)

    summaries = await round_service.list_rounds()
    if not summaries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rounds recorded yet",
        )

    rounds = []
    for s in summaries[:5]:
        try:
            rounds.append(await round_service.get_round(s.id))
        except RoundNotFoundError:
            continue

    if not rounds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rounds with data found",
        )

    qa_entry = await insights_service.answer_question(
        rounds,
        question_clean,
        handicap_index=await settings_repo.get("handicap_index"),
    )
    context = await build_home_context(
        catalog_service, round_service, settings_repo, insights_service,
    )
    context["qa_entry"] = qa_entry
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request, name="home.html", context=context,
        ),
    )
