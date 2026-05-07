"""Business logic for practice benchmark sessions."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from golf_scorecards.practice.models import (
    PracticeAttempt,
    PracticeSession,
    PracticeSessionSummary,
)
from golf_scorecards.practice.repository import PracticeRepository
from golf_scorecards.practice.stations import get_station, station_order


class PracticeSessionNotFoundError(ValueError):
    """Raised when a session ID does not exist."""


class PracticeService:
    """High-level operations for practice benchmark sessions.

    Orchestrates session creation, attempt recording, listing, deletion,
    and stat computation. Delegates persistence to ``PracticeRepository``.

    Args:
        repository: The practice repository for database access.
    """

    def __init__(self, repository: PracticeRepository) -> None:
        self._repo = repository

    # ── Session lifecycle ────────────────────────────────

    async def create_session(
        self,
        title: str | None = None,
        session_date: date | None = None,
        notes: str | None = None,
    ) -> PracticeSession:
        """Create a new empty practice session and persist it.

        Generates a unique hex UUID and timestamps the session at creation.

        Args:
            title: Optional location/label (e.g. "Practice green 2, Solastranden").
                   Falls back to "Session" in the UI if not provided.
            session_date: Date the session is performed. Defaults to today.
            notes: Optional free-text notes (e.g. weather, conditions).

        Returns:
            The newly created ``PracticeSession`` with an empty attempts list.
        """
        session = PracticeSession(
            id=uuid.uuid4().hex,
            title=title or None,
            session_date=session_date or date.today(),
            notes=notes,
            created_at=datetime.now(),
            attempts=[],
        )
        await self._repo.create_session(session)
        return session

    async def get_session(self, session_id: str) -> PracticeSession:
        """Fetch a session by ID, including all recorded attempts.

        Args:
            session_id: The hex UUID of the session.

        Returns:
            The full ``PracticeSession`` with its attempts.

        Raises:
            PracticeSessionNotFoundError: If no session exists with this ID.
        """
        session = await self._repo.get_session(session_id)
        if session is None:
            raise PracticeSessionNotFoundError(f"Session {session_id!r} not found")
        return session

    async def list_sessions(self, limit: int = 50) -> list[PracticeSessionSummary]:
        """List sessions with summary stats, newest first.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            A list of ``PracticeSessionSummary`` with total strokes and attempt counts.
        """
        return await self._repo.list_sessions(limit)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all its attempts.

        Args:
            session_id: The hex UUID of the session to delete.

        Raises:
            PracticeSessionNotFoundError: If no session exists with this ID.
        """
        deleted = await self._repo.delete_session(session_id)
        if not deleted:
            raise PracticeSessionNotFoundError(f"Session {session_id!r} not found")

    # ── Attempt recording ────────────────────────────────

    async def record_attempt(
        self,
        session_id: str,
        station_slug: str,
        attempt_number: int,
        strokes: int,
        nfs: bool = False,
    ) -> PracticeAttempt:
        """Record a single hole-out attempt for a station.

        Validates that the station slug exists in the catalog before persisting.
        If an attempt with the same (session, station, number) already exists,
        it will be overwritten (upsert semantics).

        Args:
            session_id: The session this attempt belongs to.
            station_slug: Station identifier (e.g. "putt-medium", "pitch-60").
            attempt_number: 1-based ball number within the station (1–7).
            strokes: Total strokes taken to hole out.
            nfs: Whether a non-functional strike occurred on this attempt.

        Returns:
            The persisted ``PracticeAttempt``.

        Raises:
            KeyError: If ``station_slug`` is not a valid station.
        """
        get_station(station_slug)

        attempt = PracticeAttempt(
            id=uuid.uuid4().hex,
            session_id=session_id,
            station_slug=station_slug,
            attempt_number=attempt_number,
            strokes=strokes,
            nfs=nfs,
        )
        await self._repo.save_attempt(attempt)
        return attempt

    # ── Stats ────────────────────────────────────────────

    def compute_stats(self, session: PracticeSession) -> dict:
        """Compute derived performance stats for a session.

        Metrics computed:
            - **total_strokes**: Sum of all strokes across all attempts.
            - **total_attempts**: Number of balls holed out.
            - **avg_strokes**: Mean strokes per attempt (rounded to 2 dp).
            - **up_and_down_pct**: Percentage of attempts holed in ≤2 strokes.
            - **down_in_3_pct**: Percentage of attempts holed in ≤3 strokes.
            - **station_stats**: Per-station breakdown with attempts, total_strokes,
              avg_strokes, and up_and_down_pct.

        If the session has no attempts, returns zeroed totals with ``None``
        for percentage fields.

        Args:
            session: A session with its attempts list populated.

        Returns:
            A dict keyed by metric name. Station stats are nested under
            ``station_stats[slug]``.
        """
        attempts = session.attempts
        if not attempts:
            return {
                "total_strokes": 0,
                "total_attempts": 0,
                "avg_strokes": None,
                "up_and_down_pct": None,
                "down_in_3_pct": None,
                "station_stats": {},
            }

        total_strokes = sum(a.strokes for a in attempts)
        avg_strokes = round(total_strokes / len(attempts), 2)

        # Up-and-down: holed in ≤2 strokes
        up_and_down_count = sum(1 for a in attempts if a.strokes <= 2)
        up_and_down_pct = round(up_and_down_count / len(attempts) * 100, 1)

        # Down-in-3: holed in ≤3 strokes
        down_in_3_count = sum(1 for a in attempts if a.strokes <= 3)
        down_in_3_pct = round(down_in_3_count / len(attempts) * 100, 1)

        # Per-station breakdown
        station_stats: dict[str, dict] = {}
        for slug in station_order():
            station_attempts = [a for a in attempts if a.station_slug == slug]
            if not station_attempts:
                continue
            st_strokes = sum(a.strokes for a in station_attempts)
            st_ud = sum(1 for a in station_attempts if a.strokes <= 2)
            station_stats[slug] = {
                "attempts": len(station_attempts),
                "total_strokes": st_strokes,
                "avg_strokes": round(st_strokes / len(station_attempts), 2),
                "up_and_down_pct": round(st_ud / len(station_attempts) * 100, 1),
            }

        return {
            "total_strokes": total_strokes,
            "total_attempts": len(attempts),
            "avg_strokes": avg_strokes,
            "up_and_down_pct": up_and_down_pct,
            "down_in_3_pct": down_in_3_pct,
            "station_stats": station_stats,
        }

    async def compute_visualization_stats(self) -> dict:
        """Compute aggregate per-station stats across all sessions for visualization.

        For putting stations, computes 1-putt%, 2-putt%, 3-putt% distributions.
        For pitch/bunker stations, computes U&D% (≤2) and D3% (≤3).

        Returns:
            A dict with ``putting`` and ``pitching`` keys, each containing
            per-station stats dicts keyed by station slug.
        """
        attempts = await self._repo.get_all_attempts()

        putting: dict[str, dict] = {}
        pitching: dict[str, dict] = {}

        for slug in station_order():
            station = get_station(slug)
            sa = [a for a in attempts if a.station_slug == slug]
            if not sa:
                continue

            n = len(sa)
            if station.category == "putt":
                one_putt = sum(1 for a in sa if a.strokes == 1)
                two_putt = sum(1 for a in sa if a.strokes == 2)
                three_plus = sum(1 for a in sa if a.strokes >= 3)
                putting[slug] = {
                    "station": station,
                    "attempts": n,
                    "one_putt_pct": round(one_putt / n * 100, 1),
                    "two_putt_pct": round(two_putt / n * 100, 1),
                    "three_putt_pct": round(three_plus / n * 100, 1),
                    "avg_strokes": round(sum(a.strokes for a in sa) / n, 2),
                }
            else:
                ud = sum(1 for a in sa if a.strokes <= 2)
                d3 = sum(1 for a in sa if a.strokes <= 3)
                pitching[slug] = {
                    "station": station,
                    "attempts": n,
                    "up_and_down_pct": round(ud / n * 100, 1),
                    "down_in_3_pct": round(d3 / n * 100, 1),
                    "avg_strokes": round(sum(a.strokes for a in sa) / n, 2),
                }

        return {"putting": putting, "pitching": pitching}
