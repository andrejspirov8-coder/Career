"""Tests for database migration system across all 6 databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from career_job_search.core.sqlite import connect_sqlite, migrate_schema

# ── Fresh DB init ───────────────────────────────────────────────────


def test_opportunities_db_fresh_init(tmp_path: Path) -> None:
    from career_job_search.opportunities.repository_db import (
        SCHEMA_VERSION,
        init_db,
    )

    path = init_db(tmp_path / "opportunities.sqlite3")
    with sqlite3.connect(str(path)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION


def test_recruiter_state_db_fresh_init(tmp_path: Path) -> None:
    from career_job_search.recruiters.repository import SCHEMA_VERSION, init_db

    path = init_db(tmp_path / "recruiter_state.sqlite3")
    with sqlite3.connect(str(path)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION


def test_automation_db_fresh_init(tmp_path: Path) -> None:
    from career_job_search.automation.queue import SCHEMA_VERSION, init_db

    path = init_db(tmp_path / "automation.sqlite3")
    with sqlite3.connect(str(path)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION


def test_notifications_db_fresh_init(tmp_path: Path) -> None:
    from career_job_search.notifications.center import SCHEMA_VERSION, init_db

    path = init_db(tmp_path / "notifications.sqlite3")
    with sqlite3.connect(str(path)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION


def test_web_cache_db_fresh_init(tmp_path: Path) -> None:
    from career_job_search.recruiters.web_cache import SCHEMA_SQL, SCHEMA_VERSION

    path = tmp_path / "web_cache.sqlite3"
    with connect_sqlite(path) as con:
        migrate_schema(con, SCHEMA_SQL, SCHEMA_VERSION, db_name="web_cache")
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION


# ── Idempotent re-init ─────────────────────────────────────────────


def test_opportunities_db_idempotent_reinit(tmp_path: Path) -> None:
    from career_job_search.opportunities.repository_db import init_db

    p = tmp_path / "opp_idem.sqlite3"
    init_db(p)
    init_db(p)
    with sqlite3.connect(str(p)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None


def test_recruiter_state_db_idempotent_reinit(tmp_path: Path) -> None:
    from career_job_search.recruiters.repository import init_db

    p = tmp_path / "rec_idem.sqlite3"
    init_db(p)
    init_db(p)
    with sqlite3.connect(str(p)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None


def test_automation_db_idempotent_reinit(tmp_path: Path) -> None:
    from career_job_search.automation.queue import init_db

    p = tmp_path / "auto_idem.sqlite3"
    init_db(p)
    init_db(p)
    with sqlite3.connect(str(p)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None


def test_notifications_db_idempotent_reinit(tmp_path: Path) -> None:
    from career_job_search.notifications.center import init_db

    p = tmp_path / "notif_idem.sqlite3"
    init_db(p)
    init_db(p)
    with sqlite3.connect(str(p)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None


def test_web_cache_db_idempotent_reinit(tmp_path: Path) -> None:
    from career_job_search.recruiters.web_cache import SCHEMA_SQL, SCHEMA_VERSION

    p = tmp_path / "cache_idem.sqlite3"
    with connect_sqlite(p) as con:
        migrate_schema(con, SCHEMA_SQL, SCHEMA_VERSION, db_name="web_cache")
    with connect_sqlite(p) as con:
        migrate_schema(con, SCHEMA_SQL, SCHEMA_VERSION, db_name="web_cache")
    with sqlite3.connect(str(p)) as con:
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None


# ── Core migrate_schema unit tests ─────────────────────────────────


def test_migrate_schema_fresh_db_creates_schema_meta(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    with connect_sqlite(path) as con:
        version = migrate_schema(
            con,
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
            1,
            db_name="test",
        )
        assert version == 1
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == 1


def test_migrate_schema_version_tracking(tmp_path: Path) -> None:
    path = tmp_path / "version.db"
    with connect_sqlite(path) as con:
        v1 = migrate_schema(
            con,
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
            1,
            db_name="test",
        )
        assert v1 == 1
    with connect_sqlite(path) as con:
        v2 = migrate_schema(
            con,
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);",
            2,
            db_name="test",
        )
        assert v2 == 2
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert int(row[0]) == 2


def test_migrate_schema_no_op_when_current(tmp_path: Path) -> None:
    path = tmp_path / "noop.db"
    with connect_sqlite(path) as con:
        v1 = migrate_schema(
            con,
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
            2,
            db_name="test",
        )
        assert v1 == 2
    with connect_sqlite(path) as con:
        v2 = migrate_schema(
            con,
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
            1,  # lower version — should not downgrade
            db_name="test",
        )
        assert v2 == 2


# ── Backward compat: upgrade a v0 database ─────────────────────────


def test_migrate_schema_upgrades_v0_db(tmp_path: Path) -> None:
    path = tmp_path / "v0_upgrade.db"
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO legacy VALUES (1, 'old')")
    con.commit()
    con.close()

    with connect_sqlite(path) as con:
        version = migrate_schema(
            con,
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);",
            3,
            db_name="upgrade_test",
        )
        assert version == 3
        row = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        assert int(row[0]) == 3
        row = con.execute("SELECT name FROM legacy WHERE id = 1").fetchone()
        assert row[0] == "old"
