"""FastAPI route handlers for scorecard creation, preview, export, and round entry."""

import json
from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from golf_scorecards.catalog.service import CatalogLookupError, CatalogService
from golf_scorecards.export import ExportService
from golf_scorecards.handicap.service import HandicapLookupError, HandicapService
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.rounds.models import Round, RoundHole
from golf_scorecards.rounds.service import RoundNotFoundError, RoundService
from golf_scorecards.rounds.stats import compute_quick_stats
from golf_scorecards.scorecards.builder import ScorecardBuilder
from golf_scorecards.scorecards.forms import ScorecardFormData, parse_scorecard_form
from golf_scorecards.scorecards.models import PrintableScorecard
from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_export_service,
    get_handicap_service,
    get_insights_service,
    get_round_service,
    get_scorecard_builder,
    get_settings_repo,
    get_templates,
)

router = APIRouter()
templates = get_templates()


def _strokes_received_map(
    all_holes: list[dict[str, Any]],
    playing_handicap: int | None,
    played_hole_numbers: set[int] | None = None,
) -> dict[int, int]:
    """Compute strokes received per hole from playing handicap.

    Always distributes the full 18-hole playing handicap across all 18
    holes, then returns only the holes actually played.  For 9-hole
    rounds this correctly ignores the strokes that fall on the
    unplayed nine.

    Args:
        all_holes: Full course snapshot holes (dicts with
            ``hole_number`` and ``handicap`` keys).
        playing_handicap: The WHS 18-hole playing handicap for this tee.
        played_hole_numbers: If given, only these holes are returned.

    Returns:
        Mapping of hole number to strokes received (0, 1, 2, …).
    """
    if playing_handicap is None or not all_holes:
        return {}
    sign = 1 if playing_handicap >= 0 else -1
    base, remainder = divmod(abs(playing_handicap), len(all_holes))
    stroke_map: dict[int, int] = {h["hole_number"]: sign * base for h in all_holes}
    for h in sorted(all_holes, key=lambda c: c["handicap"])[:remainder]:
        stroke_map[h["hole_number"]] += sign
    if played_hole_numbers is not None:
        return {k: v for k, v in stroke_map.items() if k in played_hole_numbers}
    return stroke_map


def _stableford_map(
    holes: list[RoundHole],
    strokes_map: dict[int, int],
) -> dict[int, int | None]:
    """Compute Stableford points per hole.

    Points are ``max(0, 2 - (net_score - par))`` where
    ``net_score = score - strokes_received``.

    Returns:
        Mapping of hole number to Stableford points (None when no score).
    """
    result: dict[int, int | None] = {}
    for h in holes:
        if h.score is None:
            result[h.hole_number] = None
        else:
            net = h.score - strokes_map.get(h.hole_number, 0)
            result[h.hole_number] = max(0, 2 - (net - h.par))
    return result


def _total_stableford(r: Round) -> int | None:
    """Compute Stableford points relative to handicap for a round.

    Returns the difference between actual points and expected points
    (2 per scored hole).  Positive means played better than handicap.
    Returns ``None`` if no holes have been scored.
    """
    if not r.course_snapshot or not r.playing_handicap:
        return None
    snapshot = json.loads(r.course_snapshot)
    played = {h.hole_number for h in r.holes}
    strokes = _strokes_received_map(snapshot["holes"], r.playing_handicap, played)
    pts = _stableford_map(r.holes, strokes)
    scored = [v for v in pts.values() if v is not None]
    if not scored:
        return None
    expected = 2 * len(scored)
    return sum(scored) - expected


def _build_scorecard(
    form_data: ScorecardFormData,
    catalog_service: CatalogService,
    handicap_service: HandicapService,
    scorecard_builder: ScorecardBuilder,
) -> PrintableScorecard:
    """Shared scorecard construction used by preview and export routes."""
    try:
        course = catalog_service.get_course(form_data.course_slug)
    except CatalogLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    tee = None
    if form_data.tee_name is not None:
        try:
            tee = catalog_service.get_tee(form_data.course_slug, form_data.tee_name)
        except CatalogLookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    handicap = None
    if form_data.handicap_index is not None and form_data.tee_name is not None:
        profile_key = form_data.handicap_profile or "men"
        if not handicap_service.has_ratings(form_data.course_slug, form_data.tee_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No slope data available for {course.course_name} "
                    f"tee {form_data.tee_name}."
                ),
            )
        try:
            handicap = handicap_service.compute_playing_handicap(
                course_slug=form_data.course_slug,
                tee_name=form_data.tee_name,
                profile_key=profile_key,
                handicap_index=form_data.handicap_index,
            )
        except HandicapLookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    return scorecard_builder.build(
        form_data=form_data,
        course=course,
        tee=tee,
        handicap=handicap,
    )


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
    round_service: RoundService = Depends(get_round_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    insights_service: InsightsService | None = Depends(get_insights_service),
) -> HTMLResponse:
    """Render the landing page with action cards, quick stats, and recent rounds.

    Args:
        request: The incoming HTTP request.
        catalog_service: Injected catalog service for course options.
        round_service: Injected round service for recent rounds and stats.
        settings_repo: Injected settings repository for handicap index.
        insights_service: Injected insights service (None if no API key).

    Returns:
        The rendered ``home.html`` template.
    """
    course_options = catalog_service.list_course_options()
    initial_course = course_options[0]
    initial_tee = initial_course["tees"][0]

    summaries = await round_service.list_rounds()
    recent = summaries[:3]

    handicap_index = await settings_repo.get("handicap_index")

    # Load full round data for the last 5 rounds to compute quick stats
    stats = None
    round_stableford: dict[str, int] = {}
    if summaries:
        stats_rounds = []
        for s in summaries[:5]:
            try:
                r = await round_service.get_round(s.id)
                stats_rounds.append(r)
            except RoundNotFoundError:
                continue
        if stats_rounds:
            stats = compute_quick_stats(stats_rounds)
        for r in stats_rounds:
            pts = _total_stableford(r)
            if pts is not None:
                round_stableford[r.id] = pts

    # Load cached insights
    insights: list[str] = []
    if insights_service is not None:
        cached = await insights_service.get_cached_insights()
        if cached:
            insights = cached

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="home.html",
            context={
                "course_options": course_options,
                "initial_course_slug": initial_course["course_slug"],
                "initial_tee_name": initial_tee,
                "recent_rounds": recent,
                "round_stableford": round_stableford,
                "stats": stats,
                "handicap_index": handicap_index,
                "insights": insights,
            },
        ),
    )


@router.post("/settings/handicap")
async def update_handicap_index(
    handicap_index: str = Form(default=""),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Update the player's stored handicap index.

    Args:
        handicap_index: The new handicap index value from the form.
        settings_repo: Injected settings repository.

    Returns:
        A redirect back to the landing page.
    """
    value = handicap_index.strip()
    if value:
        await settings_repo.set("handicap_index", value)
    return RedirectResponse(url="/", status_code=303)


@router.post("/scorecards/preview", response_class=HTMLResponse)
async def scorecard_preview(
    request: Request,
    form_data: ScorecardFormData = Depends(parse_scorecard_form),
    catalog_service: CatalogService = Depends(get_catalog_service),
    handicap_service: HandicapService = Depends(get_handicap_service),
    scorecard_builder: ScorecardBuilder = Depends(get_scorecard_builder),
) -> HTMLResponse:
    """Build and render the scorecard preview page."""
    scorecard = _build_scorecard(
        form_data, catalog_service, handicap_service, scorecard_builder,
    )

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="scorecard_preview.html",
            context={"scorecard": scorecard},
        ),
    )


@router.post("/scorecards/export/pdf")
async def scorecard_export_pdf(
    form_data: ScorecardFormData = Depends(parse_scorecard_form),
    catalog_service: CatalogService = Depends(get_catalog_service),
    handicap_service: HandicapService = Depends(get_handicap_service),
    scorecard_builder: ScorecardBuilder = Depends(get_scorecard_builder),
    export_service: ExportService = Depends(get_export_service),
) -> Response:
    """Generate and return a PDF scorecard as a file download."""
    scorecard = _build_scorecard(
        form_data, catalog_service, handicap_service, scorecard_builder,
    )
    pdf_bytes = export_service.to_pdf(scorecard)
    date_part = scorecard.meta.round_date.isoformat() if scorecard.meta.round_date else "undated"
    tee_part = f"_{scorecard.meta.tee_name}" if scorecard.meta.tee_name else ""
    filename = (
        f"scorecard_{scorecard.meta.course_name}{tee_part}"
        f"_{date_part}.pdf"
    ).replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Round entry routes ───────────────────────────────────────────────


@router.get("/rounds/new", response_class=HTMLResponse)
async def round_create_form(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> HTMLResponse:
    """Render the round creation form (course and tee selection).

    Args:
        request: The incoming HTTP request.
        catalog_service: Injected catalog service for course options.

    Returns:
        The rendered ``round_create.html`` template.
    """
    course_options = catalog_service.list_course_options()
    initial_course = course_options[0]
    initial_tee = initial_course["tees"][0]

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_create.html",
            context={
                "course_options": course_options,
                "initial_course_slug": initial_course["course_slug"],
                "initial_tee_name": initial_tee,
            },
        ),
    )


@router.post("/rounds")
async def round_create(
    course_slug: str = Form(),
    tee_name: str = Form(),
    player_name: str = Form(default=""),
    round_date: str = Form(default=""),
    holes_played: str = Form(default="18"),
    catalog_service: CatalogService = Depends(get_catalog_service),
    handicap_service: HandicapService = Depends(get_handicap_service),
    round_service: RoundService = Depends(get_round_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Create a new round and redirect to the entry form.

    Looks up the course and tee from the catalog, creates a round with
    a course snapshot and empty hole rows, then redirects to the
    spreadsheet entry page. The player's stored handicap index is
    automatically attached to the round.

    Args:
        course_slug: URL-safe course identifier from the form.
        tee_name: Selected tee name from the form.
        player_name: Optional player name.
        round_date: Optional ISO date string.
        holes_played: Which holes to play ("18", "front_9", or "back_9").
        catalog_service: Injected catalog service.
        round_service: Injected round service.
        settings_repo: Injected settings repository for handicap index.

    Returns:
        A redirect to ``GET /rounds/{id}/edit``.

    Raises:
        HTTPException: 404 if the course or tee is not found.
    """
    try:
        course = catalog_service.get_course(course_slug)
        tee = catalog_service.get_tee(course_slug, tee_name)
    except CatalogLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    parsed_date = date.fromisoformat(round_date) if round_date else date.today()
    parsed_name = player_name.strip() or None

    hci_raw = await settings_repo.get("handicap_index")
    hci = float(hci_raw) if hci_raw else None

    # Compute playing handicap from HCI + tee ratings (men profile)
    playing_hc: int | None = None
    cr: float | None = None
    sr: int | None = None
    if hci is not None and handicap_service.has_ratings(course_slug, tee_name):
        comp = handicap_service.compute_playing_handicap(
            course_slug, tee_name, "men", hci,
        )
        playing_hc = comp.playing_handicap
        cr = comp.tee_rating.course_rating
        sr = comp.tee_rating.slope_rating

    valid_holes = {"18", "front_9", "back_9"}
    hp = holes_played if holes_played in valid_holes else "18"

    r = await round_service.create_round(
        course=course,
        tee=tee,
        round_date=parsed_date,
        player_name=parsed_name,
        handicap_index=hci,
        handicap_profile="men",
        playing_handicap=playing_hc,
        course_rating=cr,
        slope_rating=sr,
        holes_played=hp,
    )
    return RedirectResponse(url=f"/rounds/{r.id}/edit", status_code=303)


@router.get("/rounds/{round_id}/edit", response_class=HTMLResponse)
async def round_entry_form(
    request: Request,
    round_id: str,
    round_service: RoundService = Depends(get_round_service),
) -> HTMLResponse:
    """Render the spreadsheet-style hole entry form for an existing round.

    Args:
        request: The incoming HTTP request.
        round_id: The unique round identifier from the URL path.
        round_service: Injected round service.

    Returns:
        The rendered ``round_entry.html`` template.

    Raises:
        HTTPException: 404 if the round does not exist.
    """
    try:
        r = await round_service.get_round(round_id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    snapshot = json.loads(r.course_snapshot)
    played = {h.hole_number for h in r.holes}
    strokes_map = _strokes_received_map(snapshot["holes"], r.playing_handicap, played)
    stableford = _stableford_map(r.holes, strokes_map)

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_entry.html",
            context={
                "round": r,
                "snapshot": snapshot,
                "strokes_map": strokes_map,
                "stableford": stableford,
            },
        ),
    )


@router.post("/rounds/{round_id}")
async def round_save(
    request: Request,
    round_id: str,
    round_service: RoundService = Depends(get_round_service),
    handicap_service: HandicapService = Depends(get_handicap_service),
) -> RedirectResponse:
    """Save hole-by-hole metric data from the entry form.

    Parses the flat form fields (``score_1``, ``putts_1``, ``fir_1``, etc.)
    into ``RoundHole`` updates and persists them. Checkbox fields are
    treated as ``1`` when present and ``None`` when absent.

    Args:
        request: The incoming HTTP request (used to read form data).
        round_id: The unique round identifier from the URL path.
        round_service: Injected round service.

    Returns:
        A redirect back to ``GET /rounds/{id}/edit`` after saving.

    Raises:
        HTTPException: 404 if the round does not exist.
    """
    try:
        r = await round_service.get_round(round_id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    form = await request.form()

    holes: list[RoundHole] = []
    for h in r.holes:
        n = h.hole_number

        def _int(field: str) -> int | None:
            """Parse a form field as an optional integer.

            Args:
                field: The form field name.

            Returns:
                The parsed integer, or ``None`` if the field is blank.
            """
            val = str(form.get(field, "") or "").strip()
            return int(val) if val else None

        def _check(field: str) -> int | None:
            """Parse a checkbox form field as 1 (checked) or 0 (unchecked).

            Returns ``None`` only when the hole has no score (unplayed).

            Args:
                field: The form field name.

            Returns:
                ``1`` if the checkbox was checked, ``0`` if unchecked.
            """
            return 1 if form.get(field) else 0

        def _str(field: str) -> str | None:
            """Parse a form field as an optional string.

            Args:
                field: The form field name.

            Returns:
                The stripped string, or ``None`` if blank.
            """
            val = str(form.get(field, "") or "").strip()
            return val if val else None

        holes.append(
            RoundHole(
                id=h.id,
                round_id=h.round_id,
                hole_number=n,
                par=h.par,
                distance=h.distance,
                handicap=h.handicap,
                score=_int(f"score_{n}"),
                putts=_int(f"putts_{n}"),
                penalty_strokes=_int(f"penalty_{n}"),
                miss_direction=_str(f"miss_{n}"),
                up_and_down=_check(f"ud_{n}"),
                sand_save=_check(f"sand_{n}"),
                sz_in_reg=_check(f"sz_{n}"),
                down_in_3=_check(f"d3_{n}"),
                nfs=_int(f"nfs_{n}"),
                notes=_str(f"notes_{n}"),
            )
        )

    await round_service.save_holes(round_id, holes)

    # Update HCI / PH if the user changed the handicap index
    hci_raw = str(form.get("handicap_index", "") or "").strip()
    new_hci = float(hci_raw) if hci_raw else None
    if new_hci != r.handicap_index:
        playing_hc: int | None = None
        cr: float | None = r.course_rating
        sr_val: int | None = r.slope_rating
        if (
            new_hci is not None
            and handicap_service.has_ratings(r.course_slug, r.tee_name)
        ):
            comp = handicap_service.compute_playing_handicap(
                r.course_slug, r.tee_name, "men", new_hci,
            )
            playing_hc = comp.playing_handicap
            cr = comp.tee_rating.course_rating
            sr_val = comp.tee_rating.slope_rating
        await round_service.update_handicap(
            round_id, new_hci, playing_hc, cr, sr_val,
        )

    return RedirectResponse(url=f"/rounds/{round_id}", status_code=303)


# ── Round history & detail routes ────────────────────────────────────


@router.get("/rounds", response_class=HTMLResponse)
async def round_list(
    request: Request,
    round_service: RoundService = Depends(get_round_service),
) -> HTMLResponse:
    """Render the round history list.

    Args:
        request: The incoming HTTP request.
        round_service: Injected round service.

    Returns:
        The rendered ``round_list.html`` template.
    """
    summaries = await round_service.list_rounds()

    round_stableford: dict[str, int] = {}
    for s in summaries:
        try:
            r = await round_service.get_round(s.id)
            pts = _total_stableford(r)
            if pts is not None:
                round_stableford[r.id] = pts
        except RoundNotFoundError:
            continue

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_list.html",
            context={"rounds": summaries, "round_stableford": round_stableford},
        ),
    )


@router.get("/rounds/{round_id}", response_class=HTMLResponse)
async def round_detail(
    request: Request,
    round_id: str,
    round_service: RoundService = Depends(get_round_service),
) -> HTMLResponse:
    """Render the read-only detail view for a saved round.

    Args:
        request: The incoming HTTP request.
        round_id: The unique round identifier from the URL path.
        round_service: Injected round service.

    Returns:
        The rendered ``round_detail.html`` template.

    Raises:
        HTTPException: 404 if the round does not exist.
    """
    try:
        r = await round_service.get_round(round_id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    snapshot = json.loads(r.course_snapshot)
    played = {h.hole_number for h in r.holes}
    strokes_map = _strokes_received_map(snapshot["holes"], r.playing_handicap, played)
    stableford = _stableford_map(r.holes, strokes_map)

    # Compute summary stats for the detail header
    scored_holes = [h for h in r.holes if h.score is not None]
    total_score: int | None = sum(
        cast(int, h.score) for h in scored_holes
    ) if scored_holes else None
    total_putts = sum(h.putts for h in scored_holes if h.putts is not None)
    total_par = sum(h.par for h in scored_holes)
    total_stableford = (
        sum(v for v in stableford.values() if v is not None)
        if scored_holes
        else None
    )

    stats = {
        "total_score": total_score,
        "total_par": total_par,
        "score_vs_par": (total_score - total_par) if total_score is not None else None,
        "total_putts": total_putts,
        "total_stableford": total_stableford,
    }

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_detail.html",
            context={
                "round": r,
                "snapshot": snapshot,
                "stats": stats,
                "strokes_map": strokes_map,
                "stableford": stableford,
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

    Redirects to the URL given by the ``next`` query parameter if present,
    otherwise falls back to ``GET /rounds``.

    Args:
        request: The incoming HTTP request.
        round_id: The unique round identifier from the URL path.
        round_service: Injected round service.

    Returns:
        A redirect to the ``next`` URL or ``GET /rounds``.

    Raises:
        HTTPException: 404 if the round does not exist.
    """
    try:
        await round_service.delete_round(round_id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    next_url = request.query_params.get("next", "/rounds")
    allowed = {"/", "/rounds"}
    redirect = next_url if next_url in allowed else "/rounds"
    return RedirectResponse(url=redirect, status_code=303)


@router.post("/insights/refresh")
async def insights_refresh(
    round_service: RoundService = Depends(get_round_service),
    insights_service: InsightsService | None = Depends(get_insights_service),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> RedirectResponse:
    """Generate fresh coaching insights from recent rounds.

    Loads the last 5 rounds, calls the OpenAI chat completion API,
    caches the result, and redirects back to the landing page.

    Args:
        round_service: Injected round service for loading rounds.
        insights_service: Injected insights service (None if no API key).

    Returns:
        A redirect to the landing page.

    Raises:
        HTTPException: 400 if no API key is configured or no rounds exist.
    """
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
            r = await round_service.get_round(s.id)
            rounds.append(r)
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
