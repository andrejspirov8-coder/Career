from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MIGRATION_HELPER = Path(__file__).parents[1] / "supabase" / "migrate_private.py"
JWT_SHAPED_VALUE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def test_supabase_migration_helper_is_secret_free_and_has_no_database_driver() -> None:
    source = MIGRATION_HELPER.read_text(encoding="utf-8")

    assert not JWT_SHAPED_VALUE.search(source)
    assert "SUPABASE_SERVICE_ROLE_KEY" not in source
    assert "psycopg2" not in source
    assert "connect(" not in source


def test_supabase_migration_helper_fails_closed() -> None:
    result = subprocess.run(
        [sys.executable, str(MIGRATION_HELPER)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    output = f"{result.stdout}\n{result.stderr}".lower()
    assert "local sqlite" in output or "disabled" in output


def test_sqlite_pragmas_enabled() -> None:
    from tempfile import NamedTemporaryFile

    from career_job_search.opportunities.repository_db import connect

    with NamedTemporaryFile(suffix=".sqlite3") as tmp:
        conn = connect(tmp.name)
        cur = conn.cursor()
        timeout = cur.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = cur.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()

        assert timeout >= 5000
        assert journal_mode.lower() == "wal"
