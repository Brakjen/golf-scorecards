"""Pydantic models for practice sessions and attempts."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class Station(BaseModel):
    """A fixed practice station definition.

    Attributes:
        slug: URL-safe identifier (e.g. "putt-medium").
        name: Display name (e.g. "Putt 5–8m").
        category: Grouping — "putt", "pitch", or "bunker".
        distance_m: Nominal distance in metres.
        description: Short description of the station setup.
        balls: Default number of attempts at this station.
    """

    slug: str
    name: str
    category: str
    distance_m: int
    description: str
    balls: int = 7


class PracticeAttempt(BaseModel):
    """A single hole-out attempt within a practice session.

    Attributes:
        id: Unique identifier.
        session_id: Foreign key to the parent session.
        station_slug: Which station this attempt belongs to.
        attempt_number: 1-based index within the station (1–7).
        strokes: Total strokes to hole out.
        nfs: Whether a non-functional strike occurred (True/False).
    """

    id: str
    session_id: str
    station_slug: str
    attempt_number: int
    strokes: int
    nfs: bool = False


class PracticeSession(BaseModel):
    """A complete practice benchmark session.

    Attributes:
        id: Unique identifier (hex UUID).
        title: Optional location/label (e.g. "Practice green 2, Solastranden").
        session_date: Date the session was performed.
        notes: Optional free-text notes about conditions, etc.
        created_at: Timestamp when the session was started.
        attempts: All recorded attempts in this session.
    """

    id: str
    title: str | None = None
    session_date: date
    notes: str | None = None
    created_at: datetime
    attempts: list[PracticeAttempt] = []


class PracticeSessionSummary(BaseModel):
    """Lightweight summary for listing sessions.

    Attributes:
        id: Session ID.
        title: Optional session title/location.
        session_date: Date played.
        total_strokes: Sum of all attempt strokes.
        total_attempts: Number of attempts recorded.
    """

    id: str
    title: str | None = None
    session_date: date
    total_strokes: int
    total_attempts: int
