#!/usr/bin/env python3
"""Generate SQL INSERTs matching Supabase schema exactly.
Reads SQLite data and outputs proper Supabase-compatible INSERTs.

Usage:
  uv run python scripts/migrate_supabase_data.py [table1 table2 ...]
  # Pipe output to Supabase MCP execute_sql
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

JOB_ROOT = Path(__file__).resolve().parent.parent

SQLITE_DBS: dict[str, Path] = {
    "opportunities": JOB_ROOT / "state" / "opportunities.sqlite3",
    "recruiter_state": JOB_ROOT / "state" / "recruiter_state.sqlite3",
    "automation": JOB_ROOT / "state" / "automation.sqlite3",
    "notifications": JOB_ROOT / "state" / "notifications.sqlite3",
}


def _fmt(val: Any) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    s = str(val).replace("'", "''")
    return f"'{s}'"


def migrate_notification_settings():
    db = SQLITE_DBS["notifications"]
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM notification_settings").fetchall()
    conn.close()
    if not rows:
        return
    for r in rows:
        d = dict(r)
        print(
            f"INSERT INTO notification_settings (id, desktop_enabled, updated_at) "
            f"VALUES ({_fmt(d['id'])}, {_fmt(bool(d['desktop_enabled']))}, {_fmt(d['updated_at'])}) "
            f"ON CONFLICT DO NOTHING;"
        )


def migrate_notifications():
    db = SQLITE_DBS["notifications"]
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM notifications").fetchall()
    conn.close()
    if not rows:
        return
    cols = [
        "notification_id",
        "scope",
        "category",
        "kind",
        "priority",
        "lifecycle",
        "title",
        "body",
        "href",
        "occurred_at",
        "source_updated_at",
        "desktop_eligible",
        "first_seen_at",
        "last_seen_at",
        "read_at",
        "dismissed_at",
        "snoozed_until",
        "resolved_at",
        "desktop_delivered_at",
    ]
    col_list = ", ".join(cols)
    for r in rows:
        d = dict(r)
        vals = ", ".join(
            _fmt(bool(d["desktop_eligible"]))
            if c == "desktop_eligible"
            else _fmt(d.get(c))
            for c in cols
        )
        print(
            f"INSERT INTO notifications ({col_list}) VALUES ({vals}) ON CONFLICT DO NOTHING;"
        )


def migrate_source_runs():
    db = SQLITE_DBS["opportunities"]
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM source_runs").fetchall()
    conn.close()
    if not rows:
        return
    # Supabase: id, run_id, source, status, snapshot_type, item_count, duration_ms, error, created_at
    # SQLite has user_id which Supabase doesn't
    cols = [
        "id",
        "run_id",
        "source",
        "status",
        "snapshot_type",
        "item_count",
        "duration_ms",
        "error",
        "created_at",
    ]
    col_list = ", ".join(cols)
    for r in rows:
        d = dict(r)
        vals = ", ".join(_fmt(d[c]) for c in cols)
        print(
            f"INSERT INTO source_runs ({col_list}) VALUES ({vals}) ON CONFLICT DO NOTHING;"
        )


def migrate_daily_runs():
    db = SQLITE_DBS["opportunities"]
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM daily_runs").fetchall()
    conn.close()
    if not rows:
        return
    # Supabase: run_id, status, partial, output_json, created_at, updated_at
    # SQLite has user_id which Supabase doesn't
    cols = ["run_id", "status", "partial", "output_json", "created_at", "updated_at"]
    col_list = ", ".join(cols)
    for r in rows:
        d = dict(r)
        vals = ", ".join(
            _fmt(d[c]) if c != "partial" else _fmt(bool(d["partial"])) for c in cols
        )
        print(
            f"INSERT INTO daily_runs ({col_list}) VALUES ({vals}) ON CONFLICT DO NOTHING;"
        )


def migrate_opportunities():
    db = SQLITE_DBS["opportunities"]
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM opportunities").fetchall()
    conn.close()
    if not rows:
        return
    # Supabase: opportunity_id, user_id, dedupe_key, source_kind, source_url,
    #           title, company, location, status, data_json, evidence_json,
    #           match_json, created_at, updated_at
    # SQLite data_json contains evidence and match inside it
    cols = [
        "opportunity_id",
        "user_id",
        "dedupe_key",
        "source_kind",
        "source_url",
        "title",
        "company",
        "location",
        "status",
        "data_json",
        "evidence_json",
        "match_json",
        "created_at",
        "updated_at",
    ]
    col_list = ", ".join(cols)
    for r in rows:
        d = dict(r)
        try:
            dj = (
                json.loads(d["data_json"])
                if isinstance(d["data_json"], str)
                else (d["data_json"] or {})
            )
        except (json.JSONDecodeError, TypeError):
            dj = {}
        evidence = dj.get("evidence")
        match = dj.get("match")
        vals = ", ".join(
            _fmt(json.dumps(dj))
            if c == "data_json"
            else _fmt(json.dumps(evidence))
            if c == "evidence_json"
            else _fmt(json.dumps(match))
            if c == "match_json"
            else _fmt(d.get(c))
            for c in cols
        )
        print(
            f"INSERT INTO opportunities ({col_list}) VALUES ({vals}) ON CONFLICT DO NOTHING;"
        )


def migrate_opportunity_aliases():
    db = SQLITE_DBS["opportunities"]
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM opportunity_aliases").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    if not rows:
        return
    cols = [
        "alias_key",
        "alias_type",
        "opportunity_id",
        "source",
        "native_source_id",
        "created_at",
        "last_seen_at",
    ]
    col_list = ", ".join(cols)
    for r in rows:
        d = dict(r)
        vals = ", ".join(_fmt(d[c]) for c in cols)
        print(
            f"INSERT INTO opportunity_aliases ({col_list}) VALUES ({vals}) ON CONFLICT DO NOTHING;"
        )


MIGRATORS = {
    "notification_settings": migrate_notification_settings,
    "notifications": migrate_notifications,
    "source_runs": migrate_source_runs,
    "daily_runs": migrate_daily_runs,
    "opportunities": migrate_opportunities,
    "opportunity_aliases": migrate_opportunity_aliases,
}


def main():
    tables = sys.argv[1:] if len(sys.argv) > 1 else list(MIGRATORS)
    for t in tables:
        if t not in MIGRATORS:
            print(f"-- skipping unknown table: {t}", file=sys.stderr)
            continue
        print(f"-- migrating {t}")
        MIGRATORS[t]()
        print()


if __name__ == "__main__":
    main()
