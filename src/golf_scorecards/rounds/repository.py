"""SQLite persistence for rounds and round holes."""

from datetime import date, datetime

import aiosqlite

from golf_scorecards.db.connection import get_connection
from golf_scorecards.rounds.models import Round, RoundHole, RoundSummary


class RoundRepository:
    """Async CRUD operations for the ``rounds`` and ``round_holes`` tables.

    Each method opens and closes its own database connection. This avoids
    long-lived connections in an async web server context.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _conn(self) -> aiosqlite.Connection:
        """Open a new async database connection.

        Returns:
            An open ``aiosqlite.Connection`` ready for queries.
        """
        return await get_connection(self._db_path)

    # ── Create ───────────────────────────────────────────

    async def create_round(self, r: Round, user_id: str) -> None:
        """Insert a round and its pre-built hole rows in a single transaction.

        The round's holes are inserted with only the static course snapshot
        fields (par, distance, handicap). Metric fields remain ``NULL`` until
        the player saves their scorecard data via ``save_holes``.

        Args:
            r: The fully-populated round including its hole list.
            user_id: The ID of the user who owns this round.
        """
        conn = await self._conn()
        try:
            await conn.execute(
                """INSERT INTO rounds (
                    id, user_id, course_slug, tee_name, player_name, round_date,
                    tee_time, handicap_index, handicap_profile, playing_handicap,
                    course_rating, slope_rating, scoring_mode, target_score,
                    opponent_name, opponent_handicap, strokes_given,
                    team_size, teammates,
                    holes_played, notes,
                    weather_code, temperature, wind_speed, precipitation,
                    course_snapshot, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.id, user_id, r.course_slug, r.tee_name, r.player_name,
                    r.round_date.isoformat(), r.tee_time, r.handicap_index,
                    r.handicap_profile, r.playing_handicap,
                    r.course_rating, r.slope_rating, r.scoring_mode,
                    r.target_score, r.opponent_name, r.opponent_handicap,
                    r.strokes_given, r.team_size, r.teammates,
                    r.holes_played, r.notes,
                    r.weather_code, r.temperature, r.wind_speed, r.precipitation,
                    r.course_snapshot,
                    r.created_at.isoformat(), r.updated_at.isoformat(),
                ),
            )
            for h in r.holes:
                await conn.execute(
                    """INSERT INTO round_holes (
                        id, round_id, hole_number, par, distance, handicap
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (h.id, h.round_id, h.hole_number, h.par, h.distance, h.handicap),
                )
            await conn.commit()
        finally:
            await conn.close()

    # ── Read ─────────────────────────────────────────────

    async def get_round(self, round_id: str, user_id: str) -> Round | None:
        """Fetch a single round with all hole data.

        Args:
            round_id: The unique round identifier.
            user_id: The ID of the user who owns this round.

        Returns:
            The full ``Round`` with holes ordered by hole number, or ``None``
            if no round with the given ID exists for this user.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                "SELECT * FROM rounds WHERE id = ? AND user_id = ?", (round_id, user_id)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            holes = await self._load_holes(conn, round_id)
            return self._row_to_round(row, holes)
        finally:
            await conn.close()

    async def list_rounds(self, user_id: str, *, course_slug: str | None = None) -> list[RoundSummary]:
        """Return all rounds as lightweight summaries, newest first.

        Computes aggregate statistics (total score, total putts, GIR count)
        via correlated subqueries so that full hole data is not loaded.

        Args:
            user_id: The ID of the user whose rounds to list.
            course_slug: Optional filter to only return rounds for this course.

        Returns:
            A list of ``RoundSummary`` objects ordered by round date
            descending, then creation timestamp descending.
        """
        conn = await self._conn()
        try:
            where = "r.user_id = ?"
            params: list[str] = [user_id]
            if course_slug:
                where += " AND r.course_slug = ?"
                params.append(course_slug)
            cursor = await conn.execute(
                f"""SELECT r.*,
                    (SELECT SUM(rh.score) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.score IS NOT NULL) AS total_score,
                    (SELECT SUM(rh.putts) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.putts IS NOT NULL) AS total_putts,
                    (SELECT SUM(rh.up_and_down) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.up_and_down IS NOT NULL) AS ud_count,
                    (SELECT SUM(rh.down_in_3) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.down_in_3 IS NOT NULL) AS d3_count,
                    (SELECT COUNT(*) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.putts >= 3) AS three_putt_count
                FROM rounds r WHERE {where}
                ORDER BY r.round_date DESC, r.created_at DESC""",
                params,
            )
            rows = await cursor.fetchall()
            return [
                RoundSummary(
                    id=row["id"],
                    course_slug=row["course_slug"],
                    tee_name=row["tee_name"],
                    player_name=row["player_name"],
                    round_date=date.fromisoformat(row["round_date"]),
                    tee_time=row["tee_time"],
                    handicap_index=row["handicap_index"],
                    playing_handicap=row["playing_handicap"],
                    scoring_mode=row["scoring_mode"],
                    holes_played=row["holes_played"],
                    opponent_name=row["opponent_name"],
                    team_size=row["team_size"],
                    notes=row["notes"],
                    weather_code=row["weather_code"],
                    temperature=row["temperature"],
                    wind_speed=row["wind_speed"],
                    precipitation=row["precipitation"],
                    total_score=row["total_score"],
                    total_putts=row["total_putts"],
                    ud_count=row["ud_count"],
                    d3_count=row["d3_count"],
                    three_putt_count=row["three_putt_count"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]
        finally:
            await conn.close()

    # ── Update ───────────────────────────────────────────

    async def save_holes(self, round_id: str, holes: list[RoundHole]) -> None:
        """Update metric data for existing hole rows in a single transaction.

        Only updates the player-entered metric columns (score, putts, FIR,
        GIR, etc.). The static course snapshot columns (par, distance,
        handicap) are not modified. Also bumps the parent round's
        ``updated_at`` timestamp.

        Args:
            round_id: The unique round identifier.
            holes: List of hole records with updated metric values. Each
                hole is matched by ``round_id`` and ``hole_number``.
        """
        conn = await self._conn()
        try:
            for h in holes:
                await conn.execute(
                    """UPDATE round_holes SET
                        score = ?, putts = ?,
                        penalty_strokes = ?, miss_direction = ?,
                        up_and_down = ?, sand_save = ?, sz_in_reg = ?,
                        down_in_3 = ?,
                        nfs = ?, hole_result = ?, drive_used = ?, notes = ?
                    WHERE round_id = ? AND hole_number = ?""",
                    (
                        h.score, h.putts,
                        h.penalty_strokes, h.miss_direction,
                        h.up_and_down, h.sand_save, h.sz_in_reg,
                        h.down_in_3,
                        h.nfs, h.hole_result, h.drive_used, h.notes,
                        round_id, h.hole_number,
                    ),
                )
            now = datetime.now().isoformat()
            await conn.execute(
                "UPDATE rounds SET updated_at = ? WHERE id = ?", (now, round_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    # ── Delete ───────────────────────────────────────────

    async def update_notes(self, round_id: str, notes: str | None, user_id: str) -> bool:
        """Update round-level notes.

        Args:
            round_id: The unique round identifier.
            notes: Free-text notes for the round, or ``None`` to clear.
            user_id: The ID of the user who owns this round.

        Returns:
            ``True`` if the round was found and updated.
        """
        conn = await self._conn()
        try:
            now = datetime.now().isoformat()
            cursor = await conn.execute(
                "UPDATE rounds SET notes = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (notes, now, round_id, user_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def update_tee_time(self, round_id: str, tee_time: str | None, user_id: str) -> bool:
        """Update the tee time on an existing round.

        Args:
            round_id: The unique round identifier.
            tee_time: The tee time string (e.g. ``"10:30"``), or ``None`` to clear.
            user_id: The ID of the user who owns this round.

        Returns:
            ``True`` if the round was found and updated.
        """
        conn = await self._conn()
        try:
            now = datetime.now().isoformat()
            cursor = await conn.execute(
                "UPDATE rounds SET tee_time = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (tee_time, now, round_id, user_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def update_handicap(
        self,
        round_id: str,
        handicap_index: float | None,
        playing_handicap: int | None,
        course_rating: float | None = None,
        slope_rating: int | None = None,
    ) -> None:
        """Update the handicap fields on an existing round.

        Args:
            round_id: The unique round identifier.
            handicap_index: The player's WHS handicap index.
            playing_handicap: Computed playing handicap for this tee.
            course_rating: Course rating (optional update).
            slope_rating: Slope rating (optional update).
        """
        conn = await self._conn()
        try:
            now = datetime.now().isoformat()
            await conn.execute(
                """UPDATE rounds SET
                    handicap_index = ?, playing_handicap = ?,
                    course_rating = ?, slope_rating = ?,
                    updated_at = ?
                WHERE id = ?""",
                (
                    handicap_index, playing_handicap,
                    course_rating, slope_rating,
                    now, round_id,
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def delete_round(self, round_id: str, user_id: str) -> bool:
        """Delete a round and its holes via ``ON DELETE CASCADE``.

        Args:
            round_id: The unique round identifier.
            user_id: The ID of the user who owns this round.

        Returns:
            ``True`` if a round was deleted, ``False`` if no round with
            the given ID existed for this user.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                "DELETE FROM rounds WHERE id = ? AND user_id = ?", (round_id, user_id)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    # ── Birdie map ────────────────────────────────────────

    async def get_birdie_map(
        self, user_id: str, year: int | None = None, *, include_par: bool = False,
    ) -> list[dict]:
        """Return holes scored under par (or at par) per course.

        Args:
            user_id: The ID of the user.
            year: Optional year filter. ``None`` means all time.
            include_par: If ``True``, include scores equal to par as well.

        Returns:
            A list of dicts with keys ``course_slug``, ``hole_number``,
            ``par``, ``best_score``.
        """
        conn = await self._conn()
        try:
            op = "<=" if include_par else "<"
            sql = f"""
                SELECT r.course_slug, rh.hole_number, rh.par,
                       MIN(rh.score) AS best_score
                FROM round_holes rh
                JOIN rounds r ON r.id = rh.round_id
                WHERE r.user_id = ?                  AND r.scoring_mode != 'match_play'                  AND rh.score IS NOT NULL
                  AND rh.score {op} rh.par
            """
            params: list[object] = [user_id]
            if year is not None:
                sql += " AND CAST(SUBSTR(r.round_date, 1, 4) AS INTEGER) = ?"
                params.append(year)
            sql += " GROUP BY r.course_slug, rh.hole_number"
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [
                {
                    "course_slug": row["course_slug"],
                    "hole_number": row["hole_number"],
                    "par": row["par"],
                    "best_score": row["best_score"],
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def get_round_years(self, user_id: str) -> list[int]:
        """Return distinct years that have rounds, descending."""
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                """SELECT DISTINCT CAST(SUBSTR(round_date, 1, 4) AS INTEGER) AS yr
                   FROM rounds WHERE user_id = ? ORDER BY yr DESC""",
                (user_id,),
            )
            return [row["yr"] for row in await cursor.fetchall()]
        finally:
            await conn.close()

    async def get_course_hole_pars(
        self, user_id: str,
    ) -> dict[str, list[dict]]:
        """Return hole par/number for each course the user has played.

        Uses the most recent round's hole data per course.

        Returns:
            Mapping of course_slug → list of {hole_number, par} dicts.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                """SELECT r.course_slug, rh.hole_number, rh.par
                   FROM round_holes rh
                   JOIN rounds r ON r.id = rh.round_id
                   WHERE r.user_id = ?
                     AND r.scoring_mode != 'match_play'
                     AND r.id IN (
                       SELECT id FROM rounds r2
                       WHERE r2.user_id = ? AND r2.course_slug = r.course_slug
                         AND r2.scoring_mode != 'match_play'
                       ORDER BY r2.round_date DESC LIMIT 1
                     )
                   ORDER BY r.course_slug, rh.hole_number""",
                (user_id, user_id),
            )
            rows = await cursor.fetchall()
            result: dict[str, list[dict]] = {}
            for row in rows:
                slug = row["course_slug"]
                if slug not in result:
                    result[slug] = []
                result[slug].append(
                    {"hole_number": row["hole_number"], "par": row["par"]}
                )
            return result
        finally:
            await conn.close()

    # ── Helpers ──────────────────────────────────────────

    async def _load_holes(
        self, conn: aiosqlite.Connection, round_id: str,
    ) -> list[RoundHole]:
        """Load all hole records for a round, ordered by hole number.

        Args:
            conn: An open database connection to reuse.
            round_id: The unique round identifier.

        Returns:
            A list of ``RoundHole`` objects ordered by ``hole_number``.
        """
        cursor = await conn.execute(
            "SELECT * FROM round_holes WHERE round_id = ? ORDER BY hole_number",
            (round_id,),
        )
        rows = await cursor.fetchall()
        return [
            RoundHole(
                id=row["id"],
                round_id=row["round_id"],
                hole_number=row["hole_number"],
                par=row["par"],
                distance=row["distance"],
                handicap=row["handicap"],
                score=row["score"],
                putts=row["putts"],
                penalty_strokes=row["penalty_strokes"],
                miss_direction=row["miss_direction"],
                up_and_down=row["up_and_down"],
                sand_save=row["sand_save"],
                sz_in_reg=row["sz_in_reg"],
                down_in_3=row["down_in_3"],
                nfs=row["nfs"],
                hole_result=row["hole_result"],
                drive_used=row["drive_used"],
                notes=row["notes"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_round(row: aiosqlite.Row, holes: list[RoundHole]) -> Round:
        """Convert a raw database row and its holes into a ``Round`` model.

        Args:
            row: A single row from the ``rounds`` table.
            holes: Pre-loaded hole records for this round.

        Returns:
            A fully-populated ``Round`` instance.
        """
        return Round(
            id=row["id"],
            course_slug=row["course_slug"],
            tee_name=row["tee_name"],
            player_name=row["player_name"],
            round_date=date.fromisoformat(row["round_date"]),
            tee_time=row["tee_time"],
            handicap_index=row["handicap_index"],
            handicap_profile=row["handicap_profile"],
            playing_handicap=row["playing_handicap"],
            course_rating=row["course_rating"],
            slope_rating=row["slope_rating"],
            scoring_mode=row["scoring_mode"],
            target_score=row["target_score"],
            opponent_name=row["opponent_name"],
            opponent_handicap=row["opponent_handicap"],
            strokes_given=row["strokes_given"],
            team_size=row["team_size"],
            teammates=row["teammates"],
            holes_played=row["holes_played"],
            notes=row["notes"],
            weather_code=row["weather_code"],
            temperature=row["temperature"],
            wind_speed=row["wind_speed"],
            precipitation=row["precipitation"],
            course_snapshot=row["course_snapshot"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            holes=holes,
        )
