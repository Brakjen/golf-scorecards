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
        user_id: str,
        player_name: str | None = None,
        tee_time: str | None = None,
        handicap_index: float | None = None,
        handicap_profile: str | None = None,
        playing_handicap: int | None = None,
        course_rating: float | None = None,
        slope_rating: int | None = None,
        scoring_mode: str = "stroke",
        target_score: int | None = None,
        holes_played: str = "18",
        notes: str | None = None,
        opponent_name: str | None = None,
        opponent_handicap: float | None = None,
        strokes_given: int | None = None,
        team_size: int | None = None,
        teammates: str | None = None,
        weather_code: int | None = None,
        temperature: float | None = None,
        wind_speed: float | None = None,
        precipitation: float | None = None,
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
            holes_played: Which holes to include ("18", "front_9", or "back_9").

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

        tee_holes = tee.holes
        if holes_played == "front_9":
            tee_holes = [h for h in tee_holes if h.hole_number <= 9]
        elif holes_played == "back_9":
            tee_holes = [h for h in tee_holes if h.hole_number >= 10]

        holes = [
            RoundHole(
                id=uuid.uuid4().hex,
                round_id=round_id,
                hole_number=h.hole_number,
                par=h.par,
                distance=h.distance,
                handicap=h.handicap,
            )
            for h in tee_holes
        ]

        r = Round(
            id=round_id,
            course_slug=course.course_slug,
            tee_name=tee.tee_name,
            player_name=player_name,
            round_date=round_date,
            tee_time=tee_time,
            handicap_index=handicap_index,
            handicap_profile=handicap_profile,
            playing_handicap=playing_handicap,
            course_rating=course_rating,
            slope_rating=slope_rating,
            scoring_mode=scoring_mode,
            target_score=target_score,
            opponent_name=opponent_name,
            opponent_handicap=opponent_handicap,
            strokes_given=strokes_given,
            team_size=team_size,
            teammates=teammates,
            holes_played=holes_played,
            notes=notes,
            weather_code=weather_code,
            temperature=temperature,
            wind_speed=wind_speed,
            precipitation=precipitation,
            course_snapshot=snapshot,
            created_at=now,
            updated_at=now,
            holes=holes,
        )

        await self._repo.create_round(r, user_id=user_id)
        return r

    async def get_round(self, round_id: str, user_id: str) -> Round:
        """Retrieve a round by ID.

        Args:
            round_id: The unique round identifier.

        Returns:
            The full ``Round`` with all hole data.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        r = await self._repo.get_round(round_id, user_id)
        if r is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        return r

    async def list_rounds(self, user_id: str, *, course_slug: str | None = None) -> list[RoundSummary]:
        """Return all rounds as lightweight summaries, newest first.

        Args:
            user_id: The ID of the user whose rounds to list.
            course_slug: Optional filter to only return rounds for this course.

        Returns:
            A list of ``RoundSummary`` objects with aggregated statistics,
            ordered by round date descending.
        """
        return await self._repo.list_rounds(user_id, course_slug=course_slug)

    async def save_holes(self, round_id: str, holes: list[RoundHole], user_id: str) -> Round:
        """Save hole metric data and return the updated round.

        Verifies the round exists, persists the updated hole metrics, then
        re-fetches and returns the full round with the saved data.

        Args:
            round_id: The unique round identifier.
            holes: List of hole records with player-entered metric values.
            user_id: The ID of the user who owns this round.

        Returns:
            The updated ``Round`` with saved hole data.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        existing = await self._repo.get_round(round_id, user_id)
        if existing is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        await self._repo.save_holes(round_id, holes)
        updated = await self._repo.get_round(round_id, user_id)
        assert updated is not None
        return updated

    async def update_notes(self, round_id: str, notes: str | None, user_id: str) -> None:
        """Update round-level notes.

        Args:
            round_id: The unique round identifier.
            notes: Free-text notes for the round, or ``None`` to clear.
            user_id: The ID of the user who owns this round.

        Raises:
            RoundNotFoundError: If no round with the given ID exists for this user.
        """
        existing = await self._repo.get_round(round_id, user_id)
        if existing is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        await self._repo.update_notes(round_id, notes, user_id)

    async def update_tee_time(self, round_id: str, tee_time: str | None, user_id: str) -> None:
        """Update tee time on an existing round.

        Raises:
            RoundNotFoundError: If no round with the given ID exists for this user.
        """
        existing = await self._repo.get_round(round_id, user_id)
        if existing is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        await self._repo.update_tee_time(round_id, tee_time, user_id)

    async def update_handicap(
        self,
        round_id: str,
        handicap_index: float | None,
        playing_handicap: int | None,
        course_rating: float | None = None,
        slope_rating: int | None = None,
        user_id: str = "",
    ) -> Round:
        """Update handicap fields on an existing round.

        Args:
            round_id: The unique round identifier.
            handicap_index: The player's WHS handicap index.
            playing_handicap: Computed playing handicap for this tee.
            course_rating: Course rating (optional).
            slope_rating: Slope rating (optional).
            user_id: The ID of the user who owns this round.

        Returns:
            The updated ``Round``.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        existing = await self._repo.get_round(round_id, user_id)
        if existing is None:
            raise RoundNotFoundError(f"Round not found: {round_id}")
        await self._repo.update_handicap(
            round_id, handicap_index, playing_handicap,
            course_rating, slope_rating,
        )
        updated = await self._repo.get_round(round_id, user_id)
        assert updated is not None
        return updated

    async def delete_round(self, round_id: str, user_id: str) -> None:
        """Delete a round and all its hole data.

        Args:
            round_id: The unique round identifier.
            user_id: The ID of the user who owns this round.

        Raises:
            RoundNotFoundError: If no round with the given ID exists.
        """
        deleted = await self._repo.delete_round(round_id, user_id)
        if not deleted:
            raise RoundNotFoundError(f"Round not found: {round_id}")

    async def get_birdie_map(
        self, user_id: str, year: int | None = None, mode: str = "birdie",
    ) -> dict:
        """Build birdie/par map data for all courses the user has played.

        Args:
            user_id: The user ID.
            year: Optional year filter.
            mode: ``"birdie"`` for under-par only, ``"par"`` for par-or-better.

        Returns a dict with keys:
            courses: list of {slug, holes: [{hole_number, par, birdied, best_score}]}
            years: list of available years (descending)
            selected_year: the year filter applied (or None for all-time)
            mode: the active mode
        """
        include_par = mode == "par"
        course_holes = await self._repo.get_course_hole_pars(user_id)
        birdied_rows = await self._repo.get_birdie_map(
            user_id, year, include_par=include_par,
        )
        years = await self._repo.get_round_years(user_id)

        # Index birdied holes: (course_slug, hole_number) -> best_score
        birdied_index: dict[tuple[str, int], int] = {}
        for row in birdied_rows:
            birdied_index[(row["course_slug"], row["hole_number"])] = row["best_score"]

        courses = []
        for slug, holes in sorted(course_holes.items()):
            course_data = {
                "slug": slug,
                "display_name": slug.replace("-", " ").title(),
                "holes": [],
                "birdied_count": 0,
            }
            for h in holes:
                key = (slug, h["hole_number"])
                best = birdied_index.get(key)
                course_data["holes"].append({
                    "hole_number": h["hole_number"],
                    "par": h["par"],
                    "birdied": key in birdied_index,
                    "best_score": best,
                })
                if key in birdied_index:
                    course_data["birdied_count"] += 1
            courses.append(course_data)

        return {
            "courses": courses,
            "years": years,
            "selected_year": year,
            "mode": mode,
        }
