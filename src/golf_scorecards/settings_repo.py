"""Key-value settings persistence in SQLite."""

from __future__ import annotations

import aiosqlite

from golf_scorecards.db.connection import get_connection


class SettingsRepository:
    """Async get/set for the ``settings`` key-value table.

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

    async def get(self, key: str) -> str | None:
        """Retrieve a setting value by key.

        Args:
            key: The setting key.

        Returns:
            The stored value string, or ``None`` if the key does not exist.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,),
            )
            row = await cursor.fetchone()
            return row["value"] if row else None
        finally:
            await conn.close()

    async def set(self, key: str, value: str) -> None:
        """Create or update a setting.

        Args:
            key: The setting key.
            value: The value to store.
        """
        conn = await self._conn()
        try:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await conn.commit()
        finally:
            await conn.close()
