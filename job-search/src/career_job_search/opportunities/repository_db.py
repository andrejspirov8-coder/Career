"""Shared SQLite setup for the opportunity domain."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from career_job_search.core.paths import project_path
from career_job_search.core.sqlite import connect_sqlite

DEFAULT_OPPORTUNITY_DB = project_path("state", "opportunities.sqlite3")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS opportunities (
  opportunity_id TEXT PRIMARY KEY,
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
ON opportunities(dedupe_key);

CREATE INDEX IF NOT EXISTS idx_opportunities_status
ON opportunities(status);

CREATE TABLE IF NOT EXISTS opportunity_actions (
  id INTEGER PRIMARY KEY,
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
  status TEXT NOT NULL,
  partial INTEGER NOT NULL,
  output_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunity_aliases (
  alias_key TEXT PRIMARY KEY,
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
    con = connect_sqlite(path, timeout_seconds=30, row_factory=True)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def init_db(db_path: Path | str = DEFAULT_OPPORTUNITY_DB) -> Path:
    path = Path(db_path)
    with connect(path) as con:
        con.executescript(SCHEMA_SQL)
    return path
