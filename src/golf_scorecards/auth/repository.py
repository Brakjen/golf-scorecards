"""SQLite persistence for user accounts."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import aiosqlite

from golf_scorecards.auth.models import User
from golf_scorecards.db.connection import get_connection


class UserRepository:
    """Async CRUD operations for the ``users`` table.

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

    async def create_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        display_name: str,
        created_at: datetime,
    ) -> None:
        """Insert a new user row.

        Args:
            user_id: Hex UUID primary key.
            username: Unique login identifier.
            password_hash: Argon2id hash of the password.
            display_name: Friendly name for display.
            created_at: Account creation timestamp.

        Raises:
            sqlite3.IntegrityError: If the username already exists.
        """
        conn = await self._conn()
        try:
            await conn.execute(
                """INSERT INTO users (id, username, password_hash, display_name, is_admin, created_at)
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (user_id, username, password_hash, display_name, created_at.isoformat()),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_by_username(self, username: str) -> tuple[User, str] | None:
        """Fetch a user by username, including password hash.

        Args:
            username: The login identifier to look up.

        Returns:
            A tuple of ``(User, password_hash)`` or ``None`` if not found.
        """
        conn = await self._conn()
        try:
            cur = await conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = await cur.fetchone()
            if row is None:
                return None
            user = User(
                id=row["id"],
                username=row["username"],
                display_name=row["display_name"],
                is_admin=bool(row["is_admin"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            return user, row["password_hash"]
        finally:
            await conn.close()

    async def get_by_id(self, user_id: str) -> User | None:
        """Fetch a user by their ID.

        Args:
            user_id: The hex UUID of the user.

        Returns:
            A ``User`` instance or ``None`` if not found.
        """
        conn = await self._conn()
        try:
            cur = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                display_name=row["display_name"],
                is_admin=bool(row["is_admin"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        finally:
            await conn.close()

    def create_user_sync(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        username: str,
        password_hash: str,
        display_name: str,
        created_at: datetime,
    ) -> None:
        """Insert a user synchronously (for dev seeding).

        Args:
            conn: An open synchronous SQLite connection.
            user_id: Hex UUID primary key.
            username: Unique login identifier.
            password_hash: Argon2id hash of the password.
            display_name: Friendly name for display.
            created_at: Account creation timestamp.
        """
        conn.execute(
            """INSERT OR IGNORE INTO users (id, username, password_hash, display_name, is_admin, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, password_hash, display_name, 0, created_at.isoformat()),
        )

    async def list_users(self) -> list[User]:
        """Fetch all users ordered by creation date."""
        conn = await self._conn()
        try:
            cur = await conn.execute(
                "SELECT * FROM users ORDER BY created_at"
            )
            rows = await cur.fetchall()
            return [
                User(
                    id=row["id"],
                    username=row["username"],
                    display_name=row["display_name"],
                    is_admin=bool(row["is_admin"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]
        finally:
            await conn.close()
