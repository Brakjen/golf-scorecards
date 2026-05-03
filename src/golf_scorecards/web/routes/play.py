"""Play routes — start a round and edit hole-by-hole metrics.

These are the "writing" surfaces of the app: creating a round and
filling in scores. Browsing existing rounds lives in ``rounds.py``.
"""

from __future__ import annotations

import json
from datetime import date
from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.catalog.service import CatalogLookupError, CatalogService
from golf_scorecards.handicap.service import HandicapService
from golf_scorecards.rounds.models import RoundHole
from golf_scorecards.rounds.service import RoundNotFoundError, RoundService
from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_handicap_service,
    get_round_service,
    get_settings_repo,
    get_templates,
)
from golf_scorecards.web.routes._helpers import (
    stableford_map,
    strokes_received_map,
)

router = APIRouter()
templates = get_templates()


@router.get("/rounds/new", response_class=HTMLResponse)
async def round_create_form(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> HTMLResponse:
    """Render the round creation form (course and tee selection)."""
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
    """Create a new round and redirect to the entry form."""
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
    """Render the spreadsheet-style hole entry form for an existing round."""
    try:
        r = await round_service.get_round(round_id)
    except RoundNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    snapshot = json.loads(r.course_snapshot)
    played = {h.hole_number for h in r.holes}
    strokes = strokes_received_map(snapshot["holes"], r.playing_handicap, played)
    stableford = stableford_map(r.holes, strokes)

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="round_entry.html",
            context={
                "round": r,
                "snapshot": snapshot,
                "strokes_map": strokes,
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
    """Save hole-by-hole metric data from the entry form."""
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
            val = str(form.get(field, "") or "").strip()
            return int(val) if val else None

        def _check(field: str) -> int | None:
            return 1 if form.get(field) else 0

        def _str(field: str) -> str | None:
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
