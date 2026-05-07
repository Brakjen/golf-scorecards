"""Practice benchmark routes — session list, creation, entry, and summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.practice.service import PracticeService
from golf_scorecards.practice.stations import STATIONS
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
    sessions = await service.list_sessions()
    return templates.TemplateResponse(
        request=request,
        name="practice_list.html",
        context={"sessions": sessions},
    )


@router.post("/practice")
async def practice_create(
    service: PracticeService = Depends(get_practice_service),
) -> RedirectResponse:
    """Create a new practice session and redirect to the active entry page.

    Generates a fresh session with today's date, persists it, then
    redirects the user to the session's stroke-entry interface.

    Args:
        service: Injected practice service for session creation.

    Returns:
        A 303 redirect to ``/practice/{session_id}``.
    """
    session = await service.create_session()
    return RedirectResponse(url=f"/practice/{session.id}", status_code=303)


@router.get("/practice/{session_id}", response_class=HTMLResponse)
async def practice_session(
    session_id: str,
    request: Request,
    service: PracticeService = Depends(get_practice_service),
) -> HTMLResponse:
    """Render the active practice session entry page.

    Loads the session and its recorded attempts, then determines which
    station and ball number the player is currently on. If all attempts
    are complete (7 stations × 7 balls = 49), redirects to the summary.

    The template receives the full station catalog, recorded attempts
    grouped by station, and the current position (station index + ball
    number) so the UI can highlight the active entry point.

    Args:
        session_id: The hex UUID of the session from the URL path.
        request: The incoming HTTP request (needed by Jinja2 templates).
        service: Injected practice service for fetching session data.

    Returns:
        An HTML response rendering ``practice_session.html``, or a
        redirect to the summary page if the session is complete.

    Raises:
        HTTPException (404): If no session exists with the given ID
            (handled by FastAPI's exception propagation).
    """
    session = await service.get_session(session_id)
    attempts = session.attempts

    # Determine current position: find first station+ball without an attempt
    total_balls = sum(s.balls for s in STATIONS)
    recorded = {(a.station_slug, a.attempt_number) for a in attempts}

    current_station_idx = 0
    current_ball = 1
    session_complete = True

    for i, station in enumerate(STATIONS):
        for ball in range(1, station.balls + 1):
            if (station.slug, ball) not in recorded:
                current_station_idx = i
                current_ball = ball
                session_complete = False
                break
        if not session_complete:
            break

    if session_complete:
        return RedirectResponse(url=f"/practice/{session_id}/summary", status_code=303)

    current_station = STATIONS[current_station_idx]

    return templates.TemplateResponse(
        request=request,
        name="practice_session.html",
        context={
            "session": session,
            "stations": STATIONS,
            "current_station": current_station,
            "current_station_idx": current_station_idx,
            "current_ball": current_ball,
            "total_balls": total_balls,
            "attempts_count": len(attempts),
            "attempts": attempts,
        },
    )


@router.post("/practice/{session_id}/attempt")
async def practice_record_attempt(
    session_id: str,
    station_slug: str = Form(...),
    attempt_number: int = Form(...),
    strokes: int = Form(...),
    service: PracticeService = Depends(get_practice_service),
) -> RedirectResponse:
    """Record a single hole-out attempt and redirect back to the session.

    Accepts form data from the stroke buttons (1–5+), persists the attempt
    via the service layer, then redirects back to the session entry page.
    The GET handler will automatically advance to the next ball or station.

    Args:
        session_id: The hex UUID of the session from the URL path.
        station_slug: Which station this attempt belongs to (hidden form field).
        attempt_number: 1-based ball number within the station (hidden form field).
        strokes: Number of strokes to hole out (from the tapped button value).
        service: Injected practice service for recording the attempt.

    Returns:
        A 303 redirect back to ``/practice/{session_id}`` which will show
        the next ball or redirect to summary if the session is complete.
    """
    await service.record_attempt(
        session_id=session_id,
        station_slug=station_slug,
        attempt_number=attempt_number,
        strokes=strokes,
    )
    return RedirectResponse(url=f"/practice/{session_id}", status_code=303)


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
    session = await service.get_session(session_id)
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
