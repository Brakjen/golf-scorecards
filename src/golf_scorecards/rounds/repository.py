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

    async def create_round(self, r: Round) -> None:
        """Insert a round and its pre-built hole rows in a single transaction.

        The round's holes are inserted with only the static course snapshot
        fields (par, distance, handicap). Metric fields remain ``NULL`` until
        the player saves their scorecard data via ``save_holes``.

        Args:
            r: The fully-populated round including its hole list.
        """
        conn = await self._conn()
        try:
            await conn.execute(
                """INSERT INTO rounds (
                    id, course_slug, tee_name, player_name, round_date,
                    handicap_index, handicap_profile, playing_handicap,
                    course_rating, slope_rating, scoring_mode, target_score,
                    course_snapshot, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.id, r.course_slug, r.tee_name, r.player_name,
                    r.round_date.isoformat(), r.handicap_index,
                    r.handicap_profile, r.playing_handicap,
                    r.course_rating, r.slope_rating, r.scoring_mode,
                    r.target_score, r.course_snapshot,
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

    async def get_round(self, round_id: str) -> Round | None:
        """Fetch a single round with all hole data.

        Args:
            round_id: The unique round identifier.

        Returns:
            The full ``Round`` with holes ordered by hole number, or ``None``
            if no round with the given ID exists.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,))
            row = await cursor.fetchone()
            if row is None:
                return None
            holes = await self._load_holes(conn, round_id)
            return self._row_to_round(row, holes)
        finally:
            await conn.close()

    async def list_rounds(self) -> list[RoundSummary]:
        """Return all rounds as lightweight summaries, newest first.

        Computes aggregate statistics (total score, total putts, GIR count)
        via correlated subqueries so that full hole data is not loaded.

        Returns:
            A list of ``RoundSummary`` objects ordered by round date
            descending, then creation timestamp descending.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                """SELECT r.*,
                    (SELECT SUM(rh.score) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.score IS NOT NULL) AS total_score,
                    (SELECT SUM(rh.putts) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.putts IS NOT NULL) AS total_putts,
                    (SELECT SUM(rh.gir) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.gir IS NOT NULL) AS gir_count,
                    (SELECT COUNT(*) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.gir IS NOT NULL) AS gir_total,
                    (SELECT SUM(rh.up_and_down) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.up_and_down IS NOT NULL) AS ud_count,
                    (SELECT SUM(rh.down_in_3) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.down_in_3 IS NOT NULL) AS d3_count,
                    (SELECT COUNT(*) FROM round_holes rh
                     WHERE rh.round_id = r.id AND rh.putts >= 3) AS three_putt_count
                FROM rounds r ORDER BY r.round_date DESC, r.created_at DESC""",
            )
            rows = await cursor.fetchall()
            return [
                RoundSummary(
                    id=row["id"],
                    course_slug=row["course_slug"],
                    tee_name=row["tee_name"],
                    player_name=row["player_name"],
                    round_date=date.fromisoformat(row["round_date"]),
                    handicap_index=row["handicap_index"],
                    playing_handicap=row["playing_handicap"],
                    scoring_mode=row["scoring_mode"],
                    total_score=row["total_score"],
                    total_putts=row["total_putts"],
                    gir_count=row["gir_count"],
                    gir_total=row["gir_total"],
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
                        score = ?, putts = ?, fir = ?, gir = ?,
                        penalty_strokes = ?, miss_direction = ?,
                        up_and_down = ?, sand_save = ?, sz_in_reg = ?,
                        down_in_3 = ?, putt_under_4ft = ?, made_over_4ft = ?,
                        notes = ?
                    WHERE round_id = ? AND hole_number = ?""",
                    (
                        h.score, h.putts, h.fir, h.gir,
                        h.penalty_strokes, h.miss_direction,
                        h.up_and_down, h.sand_save, h.sz_in_reg,
                        h.down_in_3, h.putt_under_4ft, h.made_over_4ft,
                        h.notes, round_id, h.hole_number,
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

    async def delete_round(self, round_id: str) -> bool:
        """Delete a round and its holes via ``ON DELETE CASCADE``.

        Args:
            round_id: The unique round identifier.

        Returns:
            ``True`` if a round was deleted, ``False`` if no round with
            the given ID existed.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
            await conn.commit()
            return cursor.rowcount > 0
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
                fir=row["fir"],
                gir=row["gir"],
                penalty_strokes=row["penalty_strokes"],
                miss_direction=row["miss_direction"],
                up_and_down=row["up_and_down"],
                sand_save=row["sand_save"],
                sz_in_reg=row["sz_in_reg"],
                down_in_3=row["down_in_3"],
                putt_under_4ft=row["putt_under_4ft"],
                made_over_4ft=row["made_over_4ft"],
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
            handicap_index=row["handicap_index"],
            handicap_profile=row["handicap_profile"],
            playing_handicap=row["playing_handicap"],
            course_rating=row["course_rating"],
            slope_rating=row["slope_rating"],
            scoring_mode=row["scoring_mode"],
            target_score=row["target_score"],
            course_snapshot=row["course_snapshot"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            holes=holes,
        )
