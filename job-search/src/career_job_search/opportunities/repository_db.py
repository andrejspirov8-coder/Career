"""Shared SQLite setup for the opportunity domain."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from career_job_search.core.paths import project_path
from career_job_search.core.sqlite import connect_sqlite
from career_job_search.core.user_migration import ensure_user_id_column

DEFAULT_OPPORTUNITY_DB = project_path("state", "opportunities.sqlite3")

SCHEMA_VERSION = 2

USER_ID_DDL = "user_id TEXT NOT NULL DEFAULT 'local-user'"

USER_TABLES = (
    "opportunities",
    "opportunity_aliases",
    "opportunity_actions",
    "source_runs",
    "daily_runs",
    "deliveries",
)

SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunities (
  opportunity_id TEXT PRIMARY KEY,
  {USER_ID_DDL},
  dedupe_key TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_url TEXT,
  title TEXT,
  company TEXT,
  location TEXT,
  status TEXT NOT NULL,
  data_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_dedupe
ON opportunities(user_id, dedupe_key);

CREATE INDEX IF NOT EXISTS idx_opportunities_status
ON opportunities(status);

CREATE TABLE IF NOT EXISTS opportunity_actions (
  id INTEGER PRIMARY KEY,
  {USER_ID_DDL},
  opportunity_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  old_status TEXT,
  new_status TEXT,
  operator_source TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(opportunity_id) REFERENCES opportunities(opportunity_id)
);

CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY,
  {USER_ID_DDL},
  run_id TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  snapshot_type TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  error TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_runs_run
ON source_runs(run_id);

CREATE TABLE IF NOT EXISTS daily_runs (
  run_id TEXT PRIMARY KEY,
  {USER_ID_DDL},
  status TEXT NOT NULL,
  partial INTEGER NOT NULL,
  output_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunity_aliases (
  alias_key TEXT PRIMARY KEY,
  {USER_ID_DDL},
  alias_type TEXT NOT NULL,
  opportunity_id TEXT NOT NULL,
  source TEXT NOT NULL,
  native_source_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  FOREIGN KEY(opportunity_id) REFERENCES opportunities(opportunity_id)
);

CREATE INDEX IF NOT EXISTS idx_opportunity_aliases_opportunity
ON opportunity_aliases(opportunity_id);

CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY,
  {USER_ID_DDL},
  delivery_date TEXT NOT NULL,
  canonical_identity TEXT NOT NULL,
  opportunity_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  delivered_at TEXT NOT NULL,
  UNIQUE(delivery_date, canonical_identity)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_deliveries_identity
ON deliveries(canonical_identity);

CREATE INDEX IF NOT EXISTS idx_deliveries_run
ON deliveries(run_id);
"""


def connect(db_path: Path | str = DEFAULT_OPPORTUNITY_DB) -> sqlite3.Connection:
    path = Path(db_path)
    con = connect_sqlite(path, timeout_seconds=30, row_factory=True, wal=True)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def init_db(db_path: Path | str = DEFAULT_OPPORTUNITY_DB) -> Path:
    path = Path(db_path)
    with connect(path) as con:
        ensure_user_id_column(con, USER_TABLES)
        con.executescript(SCHEMA_SQL)
        _migrate_v2_indexes(con)
        con.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
    return path


def _migrate_v2_indexes(con: sqlite3.Connection) -> None:
    """Replace the legacy global dedupe index with the per-user composite one."""
    row = con.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    stored = int(row[0]) if row is not None else 0
    if stored >= 2:
        return
    con.execute("DROP INDEX IF EXISTS idx_opportunities_dedupe")
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_dedupe "
        "ON opportunities(user_id, dedupe_key)"
    )
