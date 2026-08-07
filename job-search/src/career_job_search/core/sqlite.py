"""Shared SQLite connection defaults; schemas remain domain-owned."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_META_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
)


def connect_sqlite(
    path: Path,
    *,
    timeout_seconds: float = 30.0,
    row_factory: bool = False,
    wal: bool = False,
) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=timeout_seconds)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    if wal:
        connection.execute("PRAGMA journal_mode = WAL")
    if row_factory:
        connection.row_factory = sqlite3.Row
    return connection


def migrate_schema(
    con: sqlite3.Connection,
    schema_sql: str,
    current_version: int,
    *,
    db_name: str = "default",
) -> int:
    """Apply `schema_sql` when the recorded schema version is behind `current_version`.

    Tracks version in a `schema_meta` table (key `schema_version`). Never
    downgrades. Returns the resulting schema version.
    """
    con.execute(_SCHEMA_META_SQL)
    row = con.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    stored = int(row[0]) if row is not None else 0
    if stored >= current_version:
        return stored
    con.executescript(schema_sql)
    con.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(current_version),),
    )
    con.commit()
    return current_version
