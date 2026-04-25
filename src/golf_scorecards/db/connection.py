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

    Args:
        db_path: Filesystem path to the SQLite database file.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_schema_sql())
    finally:
        conn.close()


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
