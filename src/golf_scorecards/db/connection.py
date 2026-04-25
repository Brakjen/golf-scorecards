"""SQLite connection lifecycle and schema initialisation."""

import sqlite3
from importlib.resources import files
from pathlib import Path

import aiosqlite


def _schema_sql() -> str:
    """Read the bundled ``schema.sql`` file from package resources.

    Returns:
        The full SQL text of the schema definition file.
    """
    return files("golf_scorecards").joinpath("db/schema.sql").read_text(encoding="utf-8")


def init_db_sync(db_path: str) -> None:
    """Create the database file and apply the schema synchronously.

    Creates parent directories if they do not exist, then executes the
    bundled ``schema.sql`` against the database. Safe to call repeatedly
    because all statements use ``CREATE TABLE IF NOT EXISTS``.

    After creating tables, applies lightweight migrations for columns
    added after initial release.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_schema_sql())
        _migrate(conn)
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive column migrations to an existing database.

    Each migration checks whether the target column already exists
    before issuing ``ALTER TABLE``, making this safe to call on every
    startup.

    Args:
        conn: An open synchronous SQLite connection.
    """
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(rounds)").fetchall()
    }
    if "holes_played" not in existing:
        conn.execute(
            "ALTER TABLE rounds ADD COLUMN holes_played TEXT NOT NULL DEFAULT '18'"
        )
        conn.commit()


async def get_connection(db_path: str) -> aiosqlite.Connection:
    """Open an async SQLite connection with WAL mode and foreign keys enabled.

    Each call opens a new connection. The caller is responsible for closing
    it when done.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Returns:
        An open ``aiosqlite.Connection`` with ``Row`` row factory,
        WAL journal mode, and foreign key enforcement enabled.
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn
