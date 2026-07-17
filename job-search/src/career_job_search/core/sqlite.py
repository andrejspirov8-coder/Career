"""Shared SQLite connection defaults; schemas remain domain-owned."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_sqlite(
    path: Path,
    *,
    timeout_seconds: float = 30.0,
    row_factory: bool = False,
) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=timeout_seconds)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    if row_factory:
        connection.row_factory = sqlite3.Row
    return connection
