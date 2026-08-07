from __future__ import annotations

from tempfile import NamedTemporaryFile

from career_job_search.opportunities.repository_db import connect


def test_sqlite_pragmas_enabled() -> None:
    with NamedTemporaryFile(suffix=".sqlite3") as tmp:
        conn = connect(tmp.name)
        cur = conn.cursor()
        timeout = cur.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = cur.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()

        assert timeout >= 5000
        assert journal_mode.lower() == "wal"
