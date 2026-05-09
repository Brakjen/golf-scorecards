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

    hole_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(round_holes)").fetchall()
    }
    if "nfs" not in hole_cols:
        conn.execute("ALTER TABLE round_holes ADD COLUMN nfs INTEGER")
        conn.commit()

    cache_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(insights_cache)").fetchall()
    }
    if "cache_key" not in cache_cols:
        conn.execute(
            "ALTER TABLE insights_cache ADD COLUMN cache_key TEXT NOT NULL DEFAULT 'dashboard'"
        )
        conn.commit()

    # Practice sessions: add title column
    practice_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(practice_sessions)").fetchall()
    }
    if practice_cols and "title" not in practice_cols:
        conn.execute("ALTER TABLE practice_sessions ADD COLUMN title TEXT")
        conn.commit()

    # Multi-user: add user_id columns
    if "user_id" not in existing:
        conn.execute("ALTER TABLE rounds ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        conn.commit()

    # Round-level notes
    if "notes" not in existing:
        conn.execute("ALTER TABLE rounds ADD COLUMN notes TEXT")
        conn.commit()
    if practice_cols and "user_id" not in practice_cols:
        conn.execute(
            "ALTER TABLE practice_sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
        )
        conn.commit()

    # Settings: recreate with composite PK if needed
    settings_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()
    }
    if settings_cols and "user_id" not in settings_cols:
        conn.execute("""CREATE TABLE IF NOT EXISTS settings_new (
            key     TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT '',
            value   TEXT NOT NULL,
            PRIMARY KEY (key, user_id)
        )""")
        conn.execute("INSERT OR IGNORE INTO settings_new (key, value) SELECT key, value FROM settings")
        conn.execute("DROP TABLE settings")
        conn.execute("ALTER TABLE settings_new RENAME TO settings")
        conn.commit()

    # Users: add is_admin column
    user_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if user_cols and "is_admin" not in user_cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()

    # Match play columns on rounds
    if "opponent_name" not in existing:
        conn.execute("ALTER TABLE rounds ADD COLUMN opponent_name TEXT")
        conn.execute("ALTER TABLE rounds ADD COLUMN opponent_handicap REAL")
        conn.execute("ALTER TABLE rounds ADD COLUMN strokes_given INTEGER")
        conn.commit()

    # Match play hole result
    if "hole_result" not in hole_cols:
        conn.execute("ALTER TABLE round_holes ADD COLUMN hole_result TEXT")
        conn.commit()

    # Scramble columns on rounds
    if "team_size" not in existing:
        conn.execute("ALTER TABLE rounds ADD COLUMN team_size INTEGER")
        conn.execute("ALTER TABLE rounds ADD COLUMN teammates TEXT")
        conn.commit()

    # Scramble drive_used on round_holes
    if "drive_used" not in hole_cols:
        conn.execute("ALTER TABLE round_holes ADD COLUMN drive_used TEXT")
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
