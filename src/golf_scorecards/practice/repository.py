"""SQLite persistence for practice sessions and attempts."""

from __future__ import annotations

from datetime import date, datetime

import aiosqlite

from golf_scorecards.db.connection import get_connection
from golf_scorecards.practice.models import (
    PracticeAttempt,
    PracticeSession,
    PracticeSessionSummary,
)


class PracticeRepository:
    """Async CRUD operations for the ``practice_sessions`` and ``practice_attempts`` tables.

    Each method opens and closes its own database connection to avoid
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

    async def create_session(self, session: PracticeSession) -> None:
        """Insert a new practice session row (without attempts).

        Only the session metadata is persisted here; attempts are recorded
        separately via :meth:`save_attempt` or :meth:`save_attempts_bulk`.

        Args:
            session: The session to persist. Must have a unique ``id``.
        """
        conn = await self._conn()
        try:
            await conn.execute(
                """INSERT INTO practice_sessions (id, title, session_date, notes, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session.id,
                    session.title,
                    session.session_date.isoformat(),
                    session.notes,
                    session.created_at.isoformat(),
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def save_attempt(self, attempt: PracticeAttempt) -> None:
        """Upsert a single attempt.

        Uses ``INSERT OR REPLACE`` keyed on the unique constraint
        ``(session_id, station_slug, attempt_number)``, so re-recording
        an attempt overwrites the previous value.

        Args:
            attempt: The attempt to persist or overwrite.
        """
        conn = await self._conn()
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO practice_attempts
                   (id, session_id, station_slug, attempt_number, strokes, nfs)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    attempt.id,
                    attempt.session_id,
                    attempt.station_slug,
                    attempt.attempt_number,
                    attempt.strokes,
                    int(attempt.nfs),
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def save_attempts_bulk(self, attempts: list[PracticeAttempt]) -> None:
        """Insert or replace multiple attempts in a single transaction.

        More efficient than calling :meth:`save_attempt` in a loop because
        all rows are written in one ``executemany`` + single commit.

        Args:
            attempts: List of attempts to persist. Empty list is a no-op.
        """
        if not attempts:
            return
        conn = await self._conn()
        try:
            await conn.executemany(
                """INSERT OR REPLACE INTO practice_attempts
                   (id, session_id, station_slug, attempt_number, strokes, nfs)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (a.id, a.session_id, a.station_slug, a.attempt_number, a.strokes, int(a.nfs))
                    for a in attempts
                ],
            )
            await conn.commit()
        finally:
            await conn.close()

    # ── Read ─────────────────────────────────────────────

    async def get_session(self, session_id: str) -> PracticeSession | None:
        """Fetch a session with all its attempts.

        Performs two queries: one for the session row, then one for all
        associated attempts ordered by station and attempt number.

        Args:
            session_id: The hex UUID of the session to retrieve.

        Returns:
            A fully-hydrated ``PracticeSession`` with its ``attempts`` list
            populated, or ``None`` if no session exists with that ID.
        """
        conn = await self._conn()
        try:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM practice_sessions WHERE id = ?", (session_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return None

            cur2 = await conn.execute(
                """SELECT * FROM practice_attempts
                   WHERE session_id = ?
                   ORDER BY station_slug, attempt_number""",
                (session_id,),
            )
            attempt_rows = await cur2.fetchall()

            attempts = [
                PracticeAttempt(
                    id=ar["id"],
                    session_id=ar["session_id"],
                    station_slug=ar["station_slug"],
                    attempt_number=ar["attempt_number"],
                    strokes=ar["strokes"],
                    nfs=bool(ar["nfs"]),
                )
                for ar in attempt_rows
            ]

            return PracticeSession(
                id=row["id"],
                title=row["title"] if "title" in row.keys() else None,
                session_date=date.fromisoformat(row["session_date"]),
                notes=row["notes"],
                created_at=datetime.fromisoformat(row["created_at"]),
                attempts=attempts,
            )
        finally:
            await conn.close()

    async def list_sessions(self, limit: int = 50) -> list[PracticeSessionSummary]:
        """List sessions with aggregate stroke/attempt counts, newest first.

        Uses a LEFT JOIN with GROUP BY to compute totals in a single query.
        Sessions with no attempts will show ``total_strokes=0, total_attempts=0``.

        Args:
            limit: Maximum number of sessions to return. Defaults to 50.

        Returns:
            A list of ``PracticeSessionSummary`` objects ordered by date descending.
        """
        conn = await self._conn()
        try:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT
                       s.id,
                       s.title,
                       s.session_date,
                       COALESCE(SUM(a.strokes), 0) AS total_strokes,
                       COUNT(a.id) AS total_attempts
                   FROM practice_sessions s
                   LEFT JOIN practice_attempts a ON a.session_id = s.id
                   GROUP BY s.id
                   ORDER BY s.session_date DESC, s.created_at DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = await cur.fetchall()
            return [
                PracticeSessionSummary(
                    id=r["id"],
                    title=r["title"],
                    session_date=date.fromisoformat(r["session_date"]),
                    total_strokes=r["total_strokes"],
                    total_attempts=r["total_attempts"],
                )
                for r in rows
            ]
        finally:
            await conn.close()

    async def get_all_attempts(self) -> list[PracticeAttempt]:
        """Fetch all practice attempts across all sessions.

        Returns:
            A flat list of all ``PracticeAttempt`` records ordered by station
            and attempt number.
        """
        conn = await self._conn()
        try:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT * FROM practice_attempts
                   ORDER BY station_slug, attempt_number"""
            )
            rows = await cur.fetchall()
            return [
                PracticeAttempt(
                    id=r["id"],
                    session_id=r["session_id"],
                    station_slug=r["station_slug"],
                    attempt_number=r["attempt_number"],
                    strokes=r["strokes"],
                    nfs=bool(r["nfs"]),
                )
                for r in rows
            ]
        finally:
            await conn.close()

    # ── Delete ───────────────────────────────────────────

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and cascade-delete its attempts.

        Enables ``PRAGMA foreign_keys`` before the DELETE so that the
        ``ON DELETE CASCADE`` on ``practice_attempts.session_id`` fires.

        Args:
            session_id: The hex UUID of the session to remove.

        Returns:
            ``True`` if a session was deleted, ``False`` if the ID was not found.
        """
        conn = await self._conn()
        try:
            await conn.execute("PRAGMA foreign_keys = ON")
            cur = await conn.execute(
                "DELETE FROM practice_sessions WHERE id = ?", (session_id,)
            )
            await conn.commit()
            return cur.rowcount > 0
        finally:
            await conn.close()
