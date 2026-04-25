"""Business logic for creating and managing rounds."""

import json
import uuid
from datetime import date, datetime

from golf_scorecards.catalog.models import Course, Tee
from golf_scorecards.rounds.models import Round, RoundHole, RoundSummary
from golf_scorecards.rounds.repository import RoundRepository


class RoundNotFoundError(ValueError):
    """Raised when a round ID does not exist."""


class RoundService:
    """High-level operations for the round lifecycle.

    Orchestrates round creation (with course snapshot), hole data saving,
    listing, retrieval, and deletion. Delegates persistence to
    ``RoundRepository``.

    Args:
        repository: The round repository for database access.
    """

    def __init__(self, repository: RoundRepository) -> None:
        self._repo = repository

    async def create_round(
        self,
        *,
        course: Course,
        tee: Tee,
        round_date: date,
        player_name: str | None = None,
        handicap_index: float | None = None,
        handicap_profile: str | None = None,
        playing_handicap: int | None = None,
        course_rating: float | None = None,
        slope_rating: int | None = None,
        scoring_mode: str = "stroke",
        target_score: int | None = None,
    ) -> Round:
        """Create a new round with empty hole rows from the course snapshot.

        Generates a UUID for the round, serialises the current course and tee
        data into a JSON snapshot (so historical rounds remain accurate even
        if the catalog changes), and creates one ``RoundHole`` row per hole
        with metric fields set to ``None``.

        Args:
            course: The catalog course to snapshot.
            tee: The selected tee within the course.
            round_date: Date the round will be or was played.
            player_name: Name of the golfer.
            handicap_index: Player's WHS handicap index.
            handicap_profile: Gender profile for handicap ("men" or "women").
            playing_handicap: Computed WHS playing handicap for this tee.
            course_rating: Course rating for the selected tee and profile.
            slope_rating: Slope rating for the selected tee and profile.
            scoring_mode: Scoring format ("stroke" or "stableford").
            target_score: Optional target score for stroke play.

        Returns:
            The newly created ``Round`` with its empty hole rows.
        """
        now = datetime.now()
        round_id = uuid.uuid4().hex

        snapshot = json.dumps(
            {
                "club_name": course.club_name,
                "course_name": course.course_name,
                "course_slug": course.course_slug,
                "tee_name": tee.tee_name,
                "par_total": tee.par_total,
                "total_distance": tee.total_distance,
                "holes": [
                    {
                        "hole_number": h.hole_number,
                        "par": h.par,
                        "distance": h.distance,
                        "handicap": h.handicap,
                    }
                    for h in tee.holes
                ],
            },
        )

        holes = [
            RoundHole(
                id=uuid.uuid4().hex,
                round_id=round_id,
                hole_number=h.hole_number,
                par=h.par,
                distance=h.distance,
                handicap=h.handicap,
            )
            for h in tee.holes
        ]

        r = Round(
            id=round_id,
            course_slug=course.course_slug,
            tee_name=tee.tee_name,
            player_name=player_name,
            round_date=round_date,
            handicap_index=handicap_index,
            handicap_profile=handicap_profile,
            playing_handicap=playing_handicap,
            course_rating=course_rating,
            slope_rating=slope_rating,
            scoring_mode=scoring_mode,
            target_score=target_score,
            course_snapshot=snapshot,
            created_at=now,
            updated_at=now,
            holes=holes,
        )

        await self._repo.create_round(r)
        return r

    async def get_round(self, round_id: str) -> Round:
        """Retrieve a round by ID.

        Args:
            round_id: The unique round identifier.

        Returns:
            The full ``Round`` with all hole data.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        r = await self._repo.get_round(round_id)
        if r is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        return r

    async def list_rounds(self) -> list[RoundSummary]:
        """Return all rounds as lightweight summaries, newest first.

        Returns:
            A list of ``RoundSummary`` objects with aggregated statistics,
            ordered by round date descending.
        """
        return await self._repo.list_rounds()

    async def save_holes(self, round_id: str, holes: list[RoundHole]) -> Round:
        """Save hole metric data and return the updated round.

        Verifies the round exists, persists the updated hole metrics, then
        re-fetches and returns the full round with the saved data.

        Args:
            round_id: The unique round identifier.
            holes: List of hole records with player-entered metric values.

        Returns:
            The updated ``Round`` with saved hole data.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        existing = await self._repo.get_round(round_id)
        if existing is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        await self._repo.save_holes(round_id, holes)
        updated = await self._repo.get_round(round_id)
        assert updated is not None
        return updated

    async def delete_round(self, round_id: str) -> None:
        """Delete a round and all its hole data.

        Args:
            round_id: The unique round identifier.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        deleted = await self._repo.delete_round(round_id)
        if not deleted:
            raise RoundNotFoundError(f"Round not found: {round_id}")
