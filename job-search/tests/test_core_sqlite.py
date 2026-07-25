from __future__ import annotations

import sqlite3
from pathlib import Path

from career_job_search.core.sqlite import connect_sqlite


def test_connect_sqlite_returns_connection(tmp_path: Path):
    path = tmp_path / "test.db"
    conn = connect_sqlite(path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_connect_sqlite_creates_file(tmp_path: Path):
    path = tmp_path / "state" / "nested" / "test.db"
    conn = connect_sqlite(path)
    conn.close()
    assert path.exists()


def test_connect_sqlite_foreign_keys_enabled(tmp_path: Path):
    path = tmp_path / "fk_test.db"
    conn = connect_sqlite(path)
    cursor = conn.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_connect_sqlite_busy_timeout_set(tmp_path: Path):
    path = tmp_path / "busy_test.db"
    conn = connect_sqlite(path)
    cursor = conn.execute("PRAGMA busy_timeout")
    assert cursor.fetchone()[0] == 30000
    conn.close()


def test_connect_sqlite_can_create_and_query(tmp_path: Path):
    path = tmp_path / "query.db"
    conn = connect_sqlite(path)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    row = conn.execute("SELECT value FROM test WHERE id = 1").fetchone()
    conn.close()
    assert row[0] == "hello"


def test_connect_sqlite_with_row_factory(tmp_path: Path):
    path = tmp_path / "row_factory.db"
    conn = connect_sqlite(path, row_factory=True)
    conn.execute("CREATE TABLE t (k TEXT, v TEXT)")
    conn.execute("INSERT INTO t VALUES ('a', '1')")
    row = conn.execute("SELECT * FROM t").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["k"] == "a"
    assert row["v"] == "1"
    conn.close()


def test_connect_sqlite_without_row_factory(tmp_path: Path):
    path = tmp_path / "no_row_factory.db"
    conn = connect_sqlite(path, row_factory=False)
    conn.execute("CREATE TABLE t (k TEXT)")
    conn.execute("INSERT INTO t VALUES ('x')")
    row = conn.execute("SELECT * FROM t").fetchone()
    assert not isinstance(row, sqlite3.Row)
    assert row[0] == "x"
    conn.close()


def test_connect_sqlite_default_timeout(tmp_path: Path):
    path = tmp_path / "timeout.db"
    conn = connect_sqlite(path)
    conn.close()


def test_connect_sqlite_multiple_connections(tmp_path: Path):
    path = tmp_path / "concurrent.db"
    conn1 = connect_sqlite(path)
    conn1.execute("CREATE TABLE t (v TEXT)")
    conn1.execute("INSERT INTO t VALUES ('shared')")
    conn1.commit()
    conn2 = connect_sqlite(path)
    row = conn2.execute("SELECT v FROM t").fetchone()
    conn1.close()
    conn2.close()
    assert row[0] == "shared"
