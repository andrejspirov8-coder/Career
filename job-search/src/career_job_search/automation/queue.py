"""SQLite queue, scheduling, and run-state ownership for local automation."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from career_job_search.core.paths import project_path
from career_job_search.core.sqlite import connect_sqlite

JOB_ROOT = project_path()
DEFAULT_AUTOMATION_DB = JOB_ROOT / "state" / "automation.sqlite3"
DEFAULT_LOG_DIR = JOB_ROOT / "state" / "automation_logs"
DEFAULT_OPPORTUNITY_CONFIG = JOB_ROOT / "config" / "opportunities.example.yaml"

RUN_KIND_DAILY_SEARCH = "daily_search"
RUN_KIND_CV_BUILD = "cv_build"
RUN_KINDS = (RUN_KIND_DAILY_SEARCH, RUN_KIND_CV_BUILD)
TERMINAL_STATUSES = frozenset({"succeeded", "partial", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset({"queued", "running", "cancel_requested"})
RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{32}$")
SCHEDULE_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
MAX_CAPTURE_BYTES = 1_000_000
WORKER_ONLINE_SECONDS = 45
STALE_RUN_MINUTES = 35
SOURCE_STALE_HOURS = 36
CATCH_UP_AFTER_MINUTES = 30

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_runs (
  run_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger_source TEXT NOT NULL,
  unique_key TEXT,
  parent_run_id TEXT,
  requested_at TEXT NOT NULL,
  scheduled_for TEXT,
  started_at TEXT,
  finished_at TEXT,
  heartbeat_at TEXT,
  worker_pid INTEGER,
  child_pid INTEGER,
  attempt INTEGER NOT NULL DEFAULT 1,
  phase TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  result_json TEXT NOT NULL DEFAULT '{}',
  stdout TEXT NOT NULL DEFAULT '',
  stderr TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(parent_run_id) REFERENCES automation_runs(run_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_runs_unique_key
ON automation_runs(unique_key)
WHERE unique_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_automation_runs_status
ON automation_runs(status, requested_at);

CREATE TABLE IF NOT EXISTS automation_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  schedule_enabled INTEGER NOT NULL DEFAULT 0,
  schedule_time TEXT NOT NULL DEFAULT '08:00',
  timezone TEXT NOT NULL DEFAULT 'Europe/Vilnius',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_workers (
  worker_id TEXT PRIMARY KEY,
  pid INTEGER NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  stopped_at TEXT
);
"""


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def connect(db_path: Path | str = DEFAULT_AUTOMATION_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = connect_sqlite(path, timeout_seconds=30, row_factory=True, wal=True)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return con


def init_db(db_path: Path | str = DEFAULT_AUTOMATION_DB) -> Path:
    path = Path(db_path)
    now = utc_now_iso()
    with connect(path) as con:
        con.executescript(SCHEMA_SQL)
        con.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        con.execute(
            """
            INSERT OR IGNORE INTO automation_settings(
              id, schedule_enabled, schedule_time, timezone, updated_at
            ) VALUES (1, 0, '08:00', 'Europe/Vilnius', ?)
            """,
            (now,),
        )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def validate_run_id(run_id: str) -> str:
    clean = run_id.strip()
    if not RUN_ID_PATTERN.fullmatch(clean):
        raise ValueError("Invalid automation run id.")
    return clean


def validate_kind(kind: str) -> str:
    if kind not in RUN_KINDS:
        raise ValueError(f"Unsupported automation kind: {kind}")
    return kind


def validate_schedule_time(schedule_time: str) -> str:
    clean = schedule_time.strip()
    if not SCHEDULE_TIME_PATTERN.fullmatch(clean):
        raise ValueError("Schedule time must use 24-hour HH:MM format.")
    return clean


def validate_timezone(timezone_name: str) -> str:
    clean = timezone_name.strip()
    try:
        ZoneInfo(clean)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {clean}") from exc
    return clean


def _row_to_run(row: sqlite3.Row, *, include_streams: bool = False) -> dict[str, Any]:
    data = {
        "run_id": str(row["run_id"]),
        "kind": str(row["kind"]),
        "status": str(row["status"]),
        "trigger_source": str(row["trigger_source"]),
        "requested_at": str(row["requested_at"]),
        "scheduled_for": row["scheduled_for"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "heartbeat_at": row["heartbeat_at"],
        "attempt": int(row["attempt"]),
        "parent_run_id": row["parent_run_id"],
        "phase": str(row["phase"]),
        "progress": int(row["progress"]),
        "result": _json_load(str(row["result_json"]), {}),
        "error": str(row["error"]),
    }
    if include_streams:
        data["stdout"] = str(row["stdout"])
        data["stderr"] = str(row["stderr"])
    return data


def get_run(
    run_id: str,
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    include_streams: bool = True,
) -> dict[str, Any] | None:
    init_db(db_path)
    clean_id = validate_run_id(run_id)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM automation_runs WHERE run_id = ?", (clean_id,)
        ).fetchone()
    return _row_to_run(row, include_streams=include_streams) if row else None


def list_runs(
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    limit: int = 30,
) -> list[dict[str, Any]]:
    init_db(db_path)
    safe_limit = min(max(int(limit), 1), 100)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT * FROM automation_runs
            ORDER BY requested_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [_row_to_run(row) for row in rows]


def get_settings(*, db_path: Path | str = DEFAULT_AUTOMATION_DB) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM automation_settings WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("Automation settings are unavailable.")
    return {
        "schedule_enabled": bool(row["schedule_enabled"]),
        "schedule_time": str(row["schedule_time"]),
        "timezone": str(row["timezone"]),
        "updated_at": str(row["updated_at"]),
    }


def update_schedule(
    *,
    enabled: bool,
    schedule_time: str,
    timezone_name: str,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
) -> dict[str, Any]:
    init_db(db_path)
    clean_time = validate_schedule_time(schedule_time)
    clean_timezone = validate_timezone(timezone_name)
    with connect(db_path) as con:
        con.execute(
            """
            UPDATE automation_settings
            SET schedule_enabled = ?, schedule_time = ?, timezone = ?, updated_at = ?
            WHERE id = 1
            """,
            (int(enabled), clean_time, clean_timezone, utc_now_iso()),
        )
    return get_settings(db_path=db_path)


def enqueue_run(
    kind: str,
    *,
    trigger_source: str = "dashboard",
    unique_key: str | None = None,
    scheduled_for: str | None = None,
    parent_run_id: str | None = None,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    dedupe_active: bool = True,
) -> tuple[dict[str, Any], bool]:
    init_db(db_path)
    clean_kind = validate_kind(kind)
    clean_trigger = trigger_source.strip()[:40] or "dashboard"
    now = utc_now_iso()

    with connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        if dedupe_active:
            active = con.execute(
                """
                SELECT * FROM automation_runs
                WHERE kind = ? AND status IN ('queued', 'running', 'cancel_requested')
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (clean_kind,),
            ).fetchone()
            if active:
                con.commit()
                return _row_to_run(active), False

        if unique_key:
            existing = con.execute(
                "SELECT * FROM automation_runs WHERE unique_key = ?", (unique_key,)
            ).fetchone()
            if existing:
                con.commit()
                return _row_to_run(existing), False

        clean_parent = validate_run_id(parent_run_id) if parent_run_id else None
        attempt = 1
        if clean_parent:
            parent = con.execute(
                "SELECT attempt FROM automation_runs WHERE run_id = ?",
                (clean_parent,),
            ).fetchone()
            if not parent:
                raise ValueError("Original automation run was not found.")
            attempt = int(parent["attempt"]) + 1

        run_id = f"run_{uuid4().hex}"
        con.execute(
            """
            INSERT INTO automation_runs(
              run_id, kind, status, trigger_source, unique_key, parent_run_id,
              requested_at, scheduled_for, attempt, phase, progress
            ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, 'waiting', 0)
            """,
            (
                run_id,
                clean_kind,
                clean_trigger,
                unique_key,
                clean_parent,
                now,
                scheduled_for,
                attempt,
            ),
        )
        row = con.execute(
            "SELECT * FROM automation_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        con.commit()
    if row is None:
        raise RuntimeError("Automation run could not be created.")
    return _row_to_run(row), True


def retry_run(
    run_id: str,
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
) -> tuple[dict[str, Any], bool]:
    original = get_run(run_id, db_path=db_path, include_streams=False)
    if original is None:
        raise ValueError("Automation run was not found.")
    if original["status"] not in TERMINAL_STATUSES:
        raise ValueError("Only completed, failed, or cancelled runs can be retried.")
    return enqueue_run(
        str(original["kind"]),
        trigger_source="retry",
        parent_run_id=str(original["run_id"]),
        db_path=db_path,
    )


def cancel_run(
    run_id: str,
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
) -> dict[str, Any]:
    init_db(db_path)
    clean_id = validate_run_id(run_id)
    now = utc_now_iso()
    with connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM automation_runs WHERE run_id = ?", (clean_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Automation run was not found.")
        status = str(row["status"])
        if status == "queued":
            con.execute(
                """
                UPDATE automation_runs
                SET status = 'cancelled', phase = 'cancelled', progress = 100,
                    finished_at = ?, heartbeat_at = ?
                WHERE run_id = ?
                """,
                (now, now, clean_id),
            )
        elif status == "running":
            con.execute(
                """
                UPDATE automation_runs
                SET status = 'cancel_requested', phase = 'stopping', heartbeat_at = ?
                WHERE run_id = ?
                """,
                (now, clean_id),
            )
        elif status == "cancel_requested":
            pass
        else:
            raise ValueError("This automation run has already finished.")
        updated = con.execute(
            "SELECT * FROM automation_runs WHERE run_id = ?", (clean_id,)
        ).fetchone()
        con.commit()
    if updated is None:
        raise RuntimeError("Automation run could not be cancelled.")
    return _row_to_run(updated)


def _recover_stale_runs(*, db_path: Path | str = DEFAULT_AUTOMATION_DB) -> int:
    init_db(db_path)
    cutoff = (utc_now() - timedelta(minutes=STALE_RUN_MINUTES)).isoformat()
    now = utc_now_iso()
    with connect(db_path) as con:
        cursor = con.execute(
            """
            UPDATE automation_runs
            SET status = 'failed', phase = 'worker_lost', progress = 100,
                finished_at = ?, error = 'The background worker stopped before this run finished.'
            WHERE status IN ('running', 'cancel_requested')
              AND COALESCE(heartbeat_at, started_at, requested_at) < ?
            """,
            (now, cutoff),
        )
    return int(cursor.rowcount)


def enqueue_due_schedule(
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    settings = get_settings(db_path=db_path)
    if not settings["schedule_enabled"]:
        return None, False

    timezone = ZoneInfo(str(settings["timezone"]))
    current = (now or utc_now()).astimezone(timezone)
    hour, minute = (int(part) for part in str(settings["schedule_time"]).split(":"))
    due_at = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if current < due_at:
        return None, False

    local_date = current.date().isoformat()
    trigger_source = (
        "schedule_catch_up"
        if current - due_at >= timedelta(minutes=CATCH_UP_AFTER_MINUTES)
        else "schedule"
    )
    return enqueue_run(
        RUN_KIND_DAILY_SEARCH,
        trigger_source=trigger_source,
        unique_key=f"daily_search:{local_date}",
        scheduled_for=due_at.astimezone(UTC).isoformat(),
        db_path=db_path,
        dedupe_active=True,
    )


def _claim_next_run(
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    worker_pid: int | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    now = utc_now_iso()
    pid = worker_pid or os.getpid()
    with connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            """
            SELECT * FROM automation_runs
            WHERE status = 'queued'
              AND (scheduled_for IS NULL OR scheduled_for <= ?)
            ORDER BY requested_at ASC
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if row is None:
            con.commit()
            return None
        run_id = str(row["run_id"])
        updated = con.execute(
            """
            UPDATE automation_runs
            SET status = 'running', started_at = ?, heartbeat_at = ?,
                worker_pid = ?, phase = 'starting', progress = 5
            WHERE run_id = ? AND status = 'queued'
            """,
            (now, now, pid, run_id),
        )
        if updated.rowcount != 1:
            con.rollback()
            return None
        claimed = con.execute(
            "SELECT * FROM automation_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        con.commit()
    return _row_to_run(claimed) if claimed else None
