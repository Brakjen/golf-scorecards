"""Practice benchmark routes — session list, creation, entry, and summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.practice.service import PracticeService
from golf_scorecards.practice.stations import STATIONS, get_station
from golf_scorecards.web.dependencies import get_practice_service, get_templates

router = APIRouter()
templates = get_templates()


@router.get("/practice", response_class=HTMLResponse)
async def practice_list(
    request: Request,
    service: PracticeService = Depends(get_practice_service),
) -> HTMLResponse:
    """Render the practice session history page.

    Fetches all past sessions (newest first) and renders them as cards
    showing total strokes, ball count, and average. Includes a form button
    to start a new session.

    Args:
        request: The incoming HTTP request (needed by Jinja2 templates).
        service: Injected practice service for fetching session data.

    Returns:
        An HTML response rendering ``practice_list.html``.
    """
    sessions = await service.list_sessions(request.state.user.id)
    return templates.TemplateResponse(
        request=request,
        name="practice_list.html",
        context={"sessions": sessions},
    )


@router.post("/practice")
async def practice_create(
    request: Request,
    title: str = Form(""),
    notes: str = Form(""),
    service: PracticeService = Depends(get_practice_service),
) -> RedirectResponse:
    """Create a new practice session and redirect to the active entry page.

    Accepts an optional title (location/label) and notes from the creation
    form. If title is blank, it will be stored as None and the UI will
    fall back to displaying the date.

    Args:
        title: Optional location name (e.g. "Solastranden practice area").
        notes: Optional free-text notes (e.g. "Windy, firm greens").
        service: Injected practice service for session creation.

    Returns:
        A 303 redirect to ``/practice/{session_id}``.
    """
    session = await service.create_session(
        user_id=request.state.user.id,
        title=title.strip() or None,
        notes=notes.strip() or None,
    )
    return RedirectResponse(url=f"/practice/{session.id}", status_code=303)


@router.get("/practice/visualize", response_class=HTMLResponse)
async def practice_visualize(
    request: Request,
    service: PracticeService = Depends(get_practice_service),
) -> HTMLResponse:
    """Render the practice visualization page with SVG course illustrations.

    Shows aggregate stats across all practice sessions visualized as:
    - A fairway+green illustration with pitch distances and D3/U&D percentages.
    - A putting green with concentric distance rings and putt outcome percentages.

    Args:
        request: The incoming HTTP request (needed by Jinja2 templates).
        service: Injected practice service for computing aggregate stats.

    Returns:
        An HTML response rendering ``practice_visualize.html``.
    """
    viz_stats = await service.compute_visualization_stats(request.state.user.id)
    return templates.TemplateResponse(
        request=request,
        name="practice_visualize.html",
        context={
            "putting": viz_stats["putting"],
            "pitching": viz_stats["pitching"],
        },
    )


@router.get("/practice/{session_id}")
async def practice_session(session_id: str) -> RedirectResponse:
    """Redirect to the session summary page.

    Args:
        session_id: The hex UUID of the session from the URL path.

    Returns:
        A 303 redirect to ``/practice/{session_id}/summary``.
    """
    return RedirectResponse(url=f"/practice/{session_id}/summary", status_code=303)


@router.post("/practice/{session_id}/attempt")
async def practice_record_attempt(
    session_id: str,
    station_slug: str = Form(...),
    attempt_number: int = Form(...),
    strokes: int = Form(...),
    return_to: str = Form(""),
    service: PracticeService = Depends(get_practice_service),
) -> RedirectResponse:
    """Record a single hole-out attempt and redirect back to the session.

    Accepts form data from the stroke buttons (1–5+), persists the attempt
    via the service layer, then redirects back to the session entry page
    or to the station view if ``return_to`` is provided.

    Args:
        session_id: The hex UUID of the session from the URL path.
        station_slug: Which station this attempt belongs to (hidden form field).
        attempt_number: 1-based ball number within the station (hidden form field).
        strokes: Number of strokes to hole out (from the tapped button value).
        return_to: Optional redirect path (used by station edit view).
        service: Injected practice service for recording the attempt.

    Returns:
        A 303 redirect back to ``/practice/{session_id}`` or to ``return_to``
        if provided.
    """
    await service.record_attempt(
        session_id=session_id,
        station_slug=station_slug,
        attempt_number=attempt_number,
        strokes=strokes,
    )
    if return_to and return_to.startswith(f"/practice/{session_id}"):
        redirect_url = return_to
    else:
        redirect_url = f"/practice/{session_id}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/practice/{session_id}/station/{station_slug}", response_class=HTMLResponse)
async def practice_station_view(
    session_id: str,
    station_slug: str,
    request: Request,
    service: PracticeService = Depends(get_practice_service),
) -> HTMLResponse:
    """Render a specific station's entry/edit view within a session.

    Allows the player to navigate to any station to review or re-record
    attempts. Shows the station's 7 ball slots with recorded strokes and
    tap-to-edit functionality. Unlike the auto-advancing main view, this
    page stays on the selected station.

    Args:
        session_id: The hex UUID of the session from the URL path.
        station_slug: The station to view (e.g. "putt-medium", "pitch-60").
        request: The incoming HTTP request (needed by Jinja2 templates).
        service: Injected practice service for fetching session data.

    Returns:
        An HTML response rendering ``practice_station.html``.
    """
    session = await service.get_session(session_id, request.state.user.id)
    station = get_station(station_slug)
    station_idx = next(i for i, s in enumerate(STATIONS) if s.slug == station_slug)

    station_attempts = {
        a.attempt_number: a
        for a in session.attempts
        if a.station_slug == station_slug
    }

    return templates.TemplateResponse(
        request=request,
        name="practice_station.html",
        context={
            "session": session,
            "station": station,
            "station_idx": station_idx,
            "stations": STATIONS,
            "station_attempts": station_attempts,
        },
    )


@router.post("/practice/{session_id}/delete")
async def practice_delete_session(
    request: Request,
    session_id: str,
    service: PracticeService = Depends(get_practice_service),
) -> RedirectResponse:
    """Delete a practice session and all its attempts.

    Args:
        session_id: The hex UUID of the session to delete.
        service: Injected practice service for deletion.

    Returns:
        A 303 redirect to the practice list page.
    """
    await service.delete_session(session_id, request.state.user.id)
    return RedirectResponse(url="/practice", status_code=303)


@router.get("/practice/{session_id}/summary", response_class=HTMLResponse)
async def practice_summary(
    session_id: str,
    request: Request,
    service: PracticeService = Depends(get_practice_service),
) -> HTMLResponse:
    """Render the session summary page with computed performance stats.

    Fetches the full session with all attempts, computes derived metrics
    (total strokes, average, U&D%, D3%, per-station breakdown), and renders
    them in a results card layout. Also provides a link back to the session
    list and the station catalog for labelling the breakdown rows.

    Args:
        session_id: The hex UUID of the session from the URL path.
        request: The incoming HTTP request (needed by Jinja2 templates).
        service: Injected practice service for fetching and computing stats.

    Returns:
        An HTML response rendering ``practice_summary.html``.

    Raises:
        PracticeSessionNotFoundError: If no session exists with the given ID.
    """
    session = await service.get_session(session_id, request.state.user.id)
    stats = service.compute_stats(session)
    return templates.TemplateResponse(
        request=request,
        name="practice_summary.html",
        context={
            "session": session,
            "stats": stats,
            "stations": STATIONS,
        },
    )
