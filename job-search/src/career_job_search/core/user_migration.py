from __future__ import annotations

import sqlite3
from collections.abc import Sequence

_USER_ID_COLUMN = "user_id"


def ensure_user_id_column(con: sqlite3.Connection, tables: Sequence[str]) -> None:
    for table in tables:
        try:
            con.execute(
                f"ALTER TABLE {table} ADD COLUMN {_USER_ID_COLUMN} TEXT NOT NULL DEFAULT 'local-user'"
            )
        except sqlite3.OperationalError:
            pass
