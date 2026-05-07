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

    async def get(self, key: str, user_id: str = "") -> str | None:
        """Retrieve a setting value by key and user.

        Args:
            key: The setting key.
            user_id: The user ID scope (empty string for global settings).

        Returns:
            The stored value string, or ``None`` if the key does not exist.
        """
        conn = await self._conn()
        try:
            cursor = await conn.execute(
                "SELECT value FROM settings WHERE key = ? AND user_id = ?", (key, user_id),
            )
            row = await cursor.fetchone()
            return row["value"] if row else None
        finally:
            await conn.close()

    async def set(self, key: str, value: str, user_id: str = "") -> None:
        """Create or update a setting.

        Args:
            key: The setting key.
            value: The value to store.
            user_id: The user ID scope (empty string for global settings).
        """
        conn = await self._conn()
        try:
            await conn.execute(
                "INSERT INTO settings (key, user_id, value) VALUES (?, ?, ?) "
                "ON CONFLICT(key, user_id) DO UPDATE SET value = excluded.value",
                (key, user_id, value),
            )
            await conn.commit()
        finally:
            await conn.close()
