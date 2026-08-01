#!/usr/bin/env python3
"""SQLite state and approval ledger for recruiter outreach workflows.

This module deliberately uses only the Python standard library so it can run
before optional project dependencies are installed. The CSV/JSONL files remain
useful as import/export artifacts; this database is the local source of truth
for approval and dispatch safety checks.
"""

from __future__ import annotations

import fcntl
import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from career_job_search.core.paths import project_path
from career_job_search.core.sqlite import connect_sqlite
from career_job_search.recruiters.identity import normalise_profile_url

JOB_ROOT = project_path()
DEFAULT_STATE_DB = JOB_ROOT / "state" / "recruiter_state.sqlite3"
DEFAULT_DISPATCH_LOCK = JOB_ROOT / "state" / "live_dispatch.lock"

SCHEMA_VERSION = 2

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recruiter_profiles (
  id INTEGER PRIMARY KEY,
  profile_url TEXT UNIQUE NOT NULL,
  name TEXT,
  title TEXT,
  company TEXT,
  location TEXT,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  dry_run INTEGER NOT NULL,
  config_hash TEXT
);

CREATE TABLE IF NOT EXISTS recruiter_decisions (
  id INTEGER PRIMARY KEY,
  profile_url TEXT NOT NULL,
  run_id TEXT NOT NULL,
  score REAL,
  tier TEXT,
  status TEXT NOT NULL,
  reason TEXT,
  note TEXT,
  note_hash TEXT,
  approved_at TEXT,
  sent_at TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(profile_url) REFERENCES recruiter_profiles(profile_url),
  FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_recruiter_decisions_profile_status
ON recruiter_decisions(profile_url, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_recruiter_decisions_approval_unique
ON recruiter_decisions(profile_url, note_hash, status)
WHERE status = 'approved';

CREATE TABLE IF NOT EXISTS approval_expirations (
  profile_url TEXT NOT NULL,
  note_hash TEXT NOT NULL,
  approved_by TEXT,
  approval_reason TEXT,
  approved_at TEXT NOT NULL,
  expires_at TEXT,
  metadata_json TEXT,
  PRIMARY KEY(profile_url, note_hash)
);

CREATE TABLE IF NOT EXISTS profile_evidence (
  profile_url TEXT PRIMARY KEY,
  source TEXT,
  company_facts_json TEXT,
  persona_evidence_json TEXT,
  cv_fit_evidence_json TEXT,
  geo_evidence_json TEXT,
  risk_flags_json TEXT,
  confidence REAL,
  run_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_actions (
  id INTEGER PRIMARY KEY,
  action_type TEXT NOT NULL,
  profile_url TEXT NOT NULL,
  note_hash TEXT,
  note TEXT,
  operator_source TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operator_actions_profile
ON operator_actions(profile_url, created_at);

CREATE TABLE IF NOT EXISTS followup_tasks (
  id INTEGER PRIMARY KEY,
  profile_url TEXT NOT NULL,
  task_type TEXT NOT NULL,
  due_at TEXT,
  status TEXT NOT NULL,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_runs (
  run_id TEXT PRIMARY KEY,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  metadata_json TEXT
);
"""

VALID_DECISION_STATUSES = frozenset(
    {
        "discovered",
        "ranked",
        "needs_review",
        "approved",
        "rejected",
        "dry_run_ready",
        "sent",
        "failed",
        "cooldown",
    }
)


@dataclass(frozen=True)
class ApprovalCheck:
    profile_url: str
    note_hash: str
    approved: bool
    reason: str


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_iso_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _is_expired(value: str) -> bool:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return False
    return parsed <= datetime.now(UTC)


def canonical_profile_url(value: str) -> str:
    """Normalize LinkedIn profile URLs enough for local dedupe and approvals."""

    return normalise_profile_url(value)


def compute_note_hash(note: str) -> str:
    return sha256((note or "").strip().encode("utf-8")).hexdigest()


def connect(db_path: Path | str = DEFAULT_STATE_DB) -> sqlite3.Connection:
    path = Path(db_path)
    con = connect_sqlite(path, timeout_seconds=30.0, row_factory=True)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    # Ensure the setting is applied before the connection is returned. Some
    # SQLite builds report the effective value only after an explicit query.
    con.execute("PRAGMA synchronous = 1")
    return con


@contextmanager
def live_dispatch_ledger_lock(
    lock_path: Path | str = DEFAULT_DISPATCH_LOCK,
):
    """Serialize the final ledger recheck and LinkedIn send across local runs."""

    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def init_db(db_path: Path | str = DEFAULT_STATE_DB) -> Path:
    path = Path(db_path)
    with connect(path) as con:
        con.executescript(SCHEMA_SQL)
        con.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
    return path


def ensure_profile(
    con: sqlite3.Connection,
    *,
    profile_url: str,
    name: str = "",
    title: str = "",
    company: str = "",
    location: str = "",
    source: str = "",
) -> str:
    canon = canonical_profile_url(profile_url)
    if not canon:
        raise ValueError("profile_url is required")
    now = utc_now_iso()
    con.execute(
        """
        INSERT INTO recruiter_profiles(
          profile_url, name, title, company, location, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_url) DO UPDATE SET
          name = COALESCE(NULLIF(excluded.name, ''), recruiter_profiles.name),
          title = COALESCE(NULLIF(excluded.title, ''), recruiter_profiles.title),
          company = COALESCE(NULLIF(excluded.company, ''), recruiter_profiles.company),
          location = COALESCE(NULLIF(excluded.location, ''), recruiter_profiles.location),
          source = COALESCE(NULLIF(excluded.source, ''), recruiter_profiles.source),
          updated_at = excluded.updated_at
        """,
        (canon, name, title, company, location, source, now, now),
    )
    return canon


def ensure_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    mode: str,
    dry_run: bool,
    config_hash: str = "",
) -> str:
    rid = (run_id or "manual").strip()
    now = utc_now_iso()
    con.execute(
        """
        INSERT INTO workflow_runs(run_id, mode, started_at, dry_run, config_hash)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO NOTHING
        """,
        (rid, mode, now, 1 if dry_run else 0, config_hash or None),
    )
    return rid


def record_decision(
    con: sqlite3.Connection,
    *,
    profile_url: str,
    run_id: str,
    status: str,
    note: str = "",
    score: float | None = None,
    tier: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    if status not in VALID_DECISION_STATUSES:
        raise ValueError(f"invalid decision status: {status}")
    canon = ensure_profile(
        con,
        profile_url=profile_url,
        name=str((metadata or {}).get("name") or ""),
        title=str((metadata or {}).get("headline") or ""),
        company=str((metadata or {}).get("company") or ""),
        location=str((metadata or {}).get("location") or ""),
        source=str((metadata or {}).get("source") or ""),
    )
    ensure_run(con, run_id=run_id, mode="recruiter_outreach", dry_run=status != "sent")
    now = utc_now_iso()
    nh = compute_note_hash(note) if note else ""
    approved_at = now if status == "approved" else None
    sent_at = now if status == "sent" else None
    meta_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    con.execute(
        """
        INSERT INTO recruiter_decisions(
          profile_url, run_id, score, tier, status, reason, note, note_hash,
          approved_at, sent_at, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_url, note_hash, status) WHERE status = 'approved'
        DO UPDATE SET
          run_id = excluded.run_id,
          score = excluded.score,
          tier = excluded.tier,
          reason = excluded.reason,
          note = excluded.note,
          approved_at = excluded.approved_at,
          metadata_json = excluded.metadata_json,
          updated_at = excluded.updated_at
        """,
        (
            canon,
            run_id,
            score,
            tier,
            status,
            reason,
            note,
            nh,
            approved_at,
            sent_at,
            meta_json,
            now,
            now,
        ),
    )
    return nh


def approve_invite(
    *,
    profile_url: str,
    note: str,
    run_id: str,
    approved_by: str = "local_operator",
    approval_reason: str = "manual_approval",
    expires_at: str = "",
    score: float | None = None,
    tier: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> str:
    init_db(db_path)
    meta = {
        **(metadata or {}),
        "approved_by": approved_by,
        "approval_reason": approval_reason,
    }
    if expires_at:
        meta["expires_at"] = expires_at
    with connect(db_path) as con:
        note_hash = record_decision(
            con,
            profile_url=profile_url,
            run_id=run_id,
            status="approved",
            note=note,
            score=score,
            tier=tier,
            reason=approval_reason,
            metadata=meta,
        )
        canon = canonical_profile_url(profile_url)
        con.execute(
            """
            INSERT INTO approval_expirations(
              profile_url, note_hash, approved_by, approval_reason, approved_at,
              expires_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_url, note_hash) DO UPDATE SET
              approved_by = excluded.approved_by,
              approval_reason = excluded.approval_reason,
              approved_at = excluded.approved_at,
              expires_at = excluded.expires_at,
              metadata_json = excluded.metadata_json
            """,
            (
                canon,
                note_hash,
                approved_by,
                approval_reason,
                utc_now_iso(),
                expires_at or None,
                json.dumps(meta, ensure_ascii=False, sort_keys=True),
            ),
        )
        return note_hash


def mark_sent(
    *,
    profile_url: str,
    note: str,
    run_id: str,
    reason: str = "linkedin_invite_sent",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> str:
    init_db(db_path)
    with connect(db_path) as con:
        return record_decision(
            con,
            profile_url=profile_url,
            run_id=run_id,
            status="sent",
            note=note,
            reason=reason,
            metadata=metadata,
        )


def sent_profile_urls_on_local_date(
    day: date | None = None,
    *,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> set[str]:
    """Return successful sends for the operator's local calendar day."""

    init_db(db_path)
    target = day or datetime.now().astimezone().date()
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT profile_url, sent_at
            FROM recruiter_decisions
            WHERE status = 'sent' AND sent_at IS NOT NULL
            """
        ).fetchall()
    sent: set[str] = set()
    for row in rows:
        sent_at = _parse_iso_datetime(str(row["sent_at"] or ""))
        if sent_at is None or sent_at.astimezone().date() != target:
            continue
        profile_url = canonical_profile_url(str(row["profile_url"] or ""))
        if profile_url:
            sent.add(profile_url)
    return sent


def approval_check(
    *,
    profile_url: str,
    note: str,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> ApprovalCheck:
    init_db(db_path)
    canon = canonical_profile_url(profile_url)
    nh = compute_note_hash(note)
    if not canon or "/in/" not in canon:
        return ApprovalCheck(canon, nh, False, "missing_profile_url")
    if not (note or "").strip():
        return ApprovalCheck(canon, nh, False, "missing_note")
    with connect(db_path) as con:
        sent = con.execute(
            """
            SELECT 1 FROM recruiter_decisions
            WHERE profile_url = ? AND status = 'sent'
            LIMIT 1
            """,
            (canon,),
        ).fetchone()
        if sent:
            return ApprovalCheck(canon, nh, False, "already_sent")
        approved = con.execute(
            """
            SELECT 1 FROM recruiter_decisions
            WHERE profile_url = ? AND note_hash = ? AND status = 'approved'
            LIMIT 1
            """,
            (canon, nh),
        ).fetchone()
        expiry = con.execute(
            """
            SELECT expires_at FROM approval_expirations
            WHERE profile_url = ? AND note_hash = ?
            LIMIT 1
            """,
            (canon, nh),
        ).fetchone()
    if not approved:
        return ApprovalCheck(canon, nh, False, "missing_matching_approval")
    if expiry and _is_expired(str(expiry["expires_at"] or "")):
        return ApprovalCheck(canon, nh, False, "expired_approval")
    return ApprovalCheck(canon, nh, True, "approved")


def approval_metadata(
    *,
    profile_url: str,
    note: str,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> dict[str, Any]:
    init_db(db_path)
    canon = canonical_profile_url(profile_url)
    nh = compute_note_hash(note)
    if not canon:
        return {}
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT d.approved_at, d.metadata_json, e.approved_by, e.approval_reason,
                   e.approved_at AS approval_recorded_at, e.expires_at
            FROM recruiter_decisions d
            LEFT JOIN approval_expirations e
              ON e.profile_url = d.profile_url AND e.note_hash = d.note_hash
            WHERE d.profile_url = ? AND d.note_hash = ? AND d.status = 'approved'
            ORDER BY d.updated_at DESC
            LIMIT 1
            """,
            (canon, nh),
        ).fetchone()
    if not row:
        return {}
    try:
        meta = json.loads(str(row["metadata_json"] or "{}"))
    except json.JSONDecodeError:
        meta = {}
    return {
        "approved_by": row["approved_by"] or meta.get("approved_by") or "",
        "approval_reason": row["approval_reason"] or meta.get("approval_reason") or "",
        "approved_at": row["approval_recorded_at"] or row["approved_at"] or "",
        "expires_at": row["expires_at"] or meta.get("expires_at") or "",
    }


def latest_approval_metadata(
    *,
    profile_url: str,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> dict[str, Any]:
    init_db(db_path)
    canon = canonical_profile_url(profile_url)
    if not canon:
        return {}
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT d.note_hash, d.approved_at, d.metadata_json, e.approved_by,
                   e.approval_reason, e.approved_at AS approval_recorded_at, e.expires_at
            FROM recruiter_decisions d
            LEFT JOIN approval_expirations e
              ON e.profile_url = d.profile_url AND e.note_hash = d.note_hash
            WHERE d.profile_url = ? AND d.status = 'approved'
            ORDER BY d.updated_at DESC
            LIMIT 1
            """,
            (canon,),
        ).fetchone()
    if not row:
        return {}
    try:
        meta = json.loads(str(row["metadata_json"] or "{}"))
    except json.JSONDecodeError:
        meta = {}
    return {
        "note_hash": row["note_hash"] or "",
        "approved_by": row["approved_by"] or meta.get("approved_by") or "",
        "approval_reason": row["approval_reason"] or meta.get("approval_reason") or "",
        "approved_at": row["approval_recorded_at"] or row["approved_at"] or "",
        "expires_at": row["expires_at"] or meta.get("expires_at") or "",
    }


def record_operator_action(
    *,
    action_type: str,
    profile_url: str,
    note: str = "",
    operator_source: str = "dashboard",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now_iso()
    with connect(db_path) as con:
        canon = ensure_profile(con, profile_url=profile_url, source=operator_source)
        nh = compute_note_hash(note) if note else ""
        cur = con.execute(
            """
            INSERT INTO operator_actions(
              action_type, profile_url, note_hash, note, operator_source,
              metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_type,
                canon,
                nh,
                note,
                operator_source,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        action_id = int(cur.lastrowid)
    return {
        "id": action_id,
        "action_type": action_type,
        "profile_url": canon,
        "note_hash": nh,
        "created_at": now,
    }


def require_approvals(
    invites: Iterable[tuple[str, str]],
    *,
    db_path: Path | str = DEFAULT_STATE_DB,
) -> list[ApprovalCheck]:
    failures: list[ApprovalCheck] = []
    for profile_url, note in invites:
        check = approval_check(profile_url=profile_url, note=note, db_path=db_path)
        if not check.approved:
            failures.append(check)
    return failures


def count_by_status(db_path: Path | str = DEFAULT_STATE_DB) -> dict[str, int]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT status, COUNT(*) AS n FROM recruiter_decisions GROUP BY status"
        ).fetchall()
    return {str(row["status"]): int(row["n"]) for row in rows}
