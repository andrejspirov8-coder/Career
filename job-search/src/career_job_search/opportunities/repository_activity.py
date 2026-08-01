"""Opportunity actions, source runs, delivery ledger, and reconciliation."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from career_job_search.core.context import current_user_id
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    company_title_location_key,
    native_source_identity,
    next_action_for_opportunity,
    utc_now_iso,
)
from career_job_search.opportunities.repository_db import (
    DEFAULT_OPPORTUNITY_DB,
    connect,
    init_db,
)
from career_job_search.opportunities.repository_discovery import (
    _row_to_opportunity,
)


def _uid() -> str:
    return current_user_id.get()


def record_action(
    *,
    opportunity: Opportunity,
    action_type: str,
    old_status: OpportunityStatus,
    operator_source: str = "dashboard",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now_iso()
    with connect(db_path) as con:
        cur = con.execute(
            """
            INSERT INTO opportunity_actions(
              user_id, opportunity_id, action_type, old_status, new_status,
              operator_source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _uid(),
                opportunity.opportunity_id,
                action_type,
                old_status.value,
                opportunity.status.value,
                operator_source,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        action_id = int(cur.lastrowid)
    return {
        "id": action_id,
        "opportunity_id": opportunity.opportunity_id,
        "action_type": action_type,
        "old_status": old_status.value,
        "new_status": opportunity.status.value,
        "created_at": now,
    }


def actions_for_opportunity(
    opportunity_id: str,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT action_type, old_status, new_status, operator_source,
                   metadata_json, created_at
            FROM opportunity_actions
            WHERE opportunity_id = ? AND user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (opportunity_id, _uid()),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        out.append(
            {
                "action_type": row["action_type"],
                "old_status": row["old_status"],
                "new_status": row["new_status"],
                "operator_source": row["operator_source"],
                "metadata": metadata,
                "created_at": row["created_at"],
            }
        )
    return out


def count_by_status(
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, int]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT status, COUNT(*) AS n FROM opportunities
            WHERE user_id = ?
            GROUP BY status
            """,
            (_uid(),),
        ).fetchall()
    return {str(row["status"]): int(row["n"]) for row in rows}


_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(token|api[_-]?key|password|secret)\s*[:=]\s*([^\s,;]+)"
)


def _redact_error(error: object) -> str:
    single_line = " ".join(str(error or "").split())
    redacted = _SECRET_VALUE_RE.sub(r"\1=[redacted]", single_line)
    if len(redacted) > 240:
        return redacted[:237].rstrip() + "..."
    return redacted


def record_source_run(
    source: str,
    status: str,
    snapshot_type: str,
    item_count: int,
    duration_ms: int,
    error: object = "",
    run_id: str | None = None,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    if snapshot_type not in {"snapshot", "incremental"}:
        raise ValueError("snapshot_type must be 'snapshot' or 'incremental'")
    init_db(db_path)
    source_run_id = run_id or f"source_{uuid4().hex}"
    created_at = utc_now_iso()
    clean_error = _redact_error(error)
    with connect(db_path) as con:
        cur = con.execute(
            """
            INSERT INTO source_runs(
              user_id, run_id, source, status, snapshot_type, item_count,
              duration_ms, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _uid(),
                source_run_id,
                source,
                status,
                snapshot_type,
                int(item_count),
                int(duration_ms),
                clean_error,
                created_at,
            ),
        )
        record_id = int(cur.lastrowid)
    return {
        "id": record_id,
        "run_id": source_run_id,
        "source": source,
        "status": status,
        "snapshot_type": snapshot_type,
        "item_count": int(item_count),
        "duration_ms": int(duration_ms),
        "error": clean_error,
        "created_at": created_at,
    }


def save_daily_run(
    run_id: str,
    status: str,
    partial: bool,
    output: Any,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now_iso()
    output_json = json.dumps(output, ensure_ascii=False, sort_keys=True)
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO daily_runs(
              user_id, run_id, status, partial, output_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              status = excluded.status,
              partial = excluded.partial,
              output_json = excluded.output_json,
              updated_at = excluded.updated_at
            """,
            (_uid(), run_id, status, int(partial), output_json, now, now),
        )
    saved = get_daily_run(run_id, db_path=db_path)
    if saved is None:
        raise RuntimeError(f"Failed to save daily run {run_id}")
    return saved


def _daily_run_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "status": str(row["status"]),
        "partial": bool(row["partial"]),
        "output": json.loads(str(row["output_json"])),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_daily_run(
    run_id: str,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any] | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT run_id, status, partial, output_json, created_at, updated_at
            FROM daily_runs
            WHERE run_id = ? AND user_id = ?
            LIMIT 1
            """,
            (run_id, _uid()),
        ).fetchone()
    return _daily_run_dict(row) if row else None


def latest_daily_run(
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any] | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT run_id, status, partial, output_json, created_at, updated_at
            FROM daily_runs
            WHERE user_id = ?
            ORDER BY updated_at DESC, rowid DESC
            LIMIT 1
            """,
            (_uid(),),
        ).fetchone()
    return _daily_run_dict(row) if row else None


def delivery_identity(opportunity: Opportunity) -> str:
    if opportunity.canonical_identity:
        return opportunity.canonical_identity
    if opportunity.native_source_id:
        return native_source_identity(opportunity.source, opportunity.native_source_id)
    return company_title_location_key(
        opportunity.company, opportunity.title, opportunity.location
    )


def claim_deliveries(
    opportunities: list[Opportunity],
    run_id: str,
    preview: bool = False,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> list[Opportunity]:
    init_db(db_path)
    delivered_at = utc_now_iso()
    delivery_date = delivered_at[:10]
    unique: list[tuple[str, Opportunity]] = []
    seen: set[str] = set()
    for opportunity in opportunities:
        identity = delivery_identity(opportunity)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append((identity, opportunity))

    if preview:
        with connect(db_path) as con:
            return [
                opportunity
                for identity, opportunity in unique
                if not _identity_delivered(con, identity)
            ]

    claimed: list[Opportunity] = []
    with connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        for identity, opportunity in unique:
            cur = con.execute(
                """
                INSERT OR IGNORE INTO deliveries(
                  user_id, delivery_date, canonical_identity, opportunity_id,
                  run_id, delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _uid(),
                    delivery_date,
                    identity,
                    opportunity.opportunity_id,
                    run_id,
                    delivered_at,
                ),
            )
            if cur.rowcount == 1:
                claimed.append(opportunity)
    return claimed


def undelivered_opportunities(
    opportunities: list[Opportunity],
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> list[Opportunity]:
    """Return candidates that have not already been written to the ledger."""

    init_db(db_path)
    unique: list[Opportunity] = []
    seen: set[str] = set()
    with connect(db_path) as con:
        for opportunity in opportunities:
            identity = delivery_identity(opportunity)
            if identity in seen or _identity_delivered(con, identity):
                continue
            seen.add(identity)
            unique.append(opportunity)
    return unique


def _identity_delivered(
    con: sqlite3.Connection,
    identity: str,
) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM deliveries
        WHERE canonical_identity = ? AND user_id = ?
        LIMIT 1
        """,
        (identity, _uid()),
    ).fetchone()
    return row is not None


def mark_unseen_opportunities_expired(
    *,
    seen_dedupe_keys: list[str],
    source_names: list[str],
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> int:
    init_db(db_path)
    if not source_names:
        return 0
    seen = set(seen_dedupe_keys)
    sources = set(source_names)
    now = utc_now_iso()
    changed = 0
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT data_json FROM opportunities WHERE user_id = ?",
            (_uid(),),
        ).fetchall()
        for row in rows:
            opportunity = _row_to_opportunity(row)
            if opportunity.source not in sources:
                continue
            if opportunity.dedupe_key in seen:
                continue
            if opportunity.status in {
                OpportunityStatus.APPLIED,
                OpportunityStatus.SKIPPED,
                OpportunityStatus.EXPIRED,
            }:
                continue
            opportunity.status = OpportunityStatus.EXPIRED
            opportunity.likely_closed = True
            opportunity.last_checked_at = now
            opportunity.evidence.risk_flags = list(
                dict.fromkeys([*opportunity.evidence.risk_flags, "likely_closed"])
            )
            opportunity.next_action = "wait"
            con.execute(
                """
                UPDATE opportunities
                SET status = ?, data_json = ?, updated_at = ?
                WHERE opportunity_id = ? AND user_id = ?
                """,
                (
                    opportunity.status.value,
                    json.dumps(
                        opportunity.to_json_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now,
                    opportunity.opportunity_id,
                    _uid(),
                ),
            )
            changed += 1
    return changed


def mark_unseen_linkedin_browser_unverified(
    *,
    seen_native_source_ids: list[str],
    snapshot_complete: bool,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> int:
    """Remove stale LinkedIn browser captures from the live delivery queue.

    The browser automation supplies a complete six-query snapshot. A listing
    absent from that snapshot is not declared closed without a detail-page
    check, but it is no longer safe to present as currently live.
    """

    if not snapshot_complete:
        return 0
    init_db(db_path)
    seen = {str(value).strip() for value in seen_native_source_ids if str(value).strip()}
    now = utc_now_iso()
    changed = 0
    preserved_statuses = {
        OpportunityStatus.APPLIED,
        OpportunityStatus.SKIPPED,
        OpportunityStatus.FOLLOW_UP,
        OpportunityStatus.EXPIRED,
    }
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT data_json FROM opportunities WHERE user_id = ?",
            (_uid(),),
        ).fetchall()
        for row in rows:
            opportunity = _row_to_opportunity(row)
            if (
                opportunity.source != "linkedin"
                or opportunity.source_kind.value != "job_board"
                or opportunity.live_check_method != "linkedin_browser"
                or opportunity.native_source_id in seen
                or opportunity.status in preserved_statuses
                or opportunity.live_status == "closed"
            ):
                continue
            opportunity.live_status = "unverified"
            opportunity.live_checked_at = now
            opportunity.live_check_method = "linkedin_reconciliation"
            opportunity.live_check_note = "not_seen_in_latest_browser_snapshot"
            opportunity.likely_closed = False
            opportunity.evidence.risk_flags = list(
                dict.fromkeys(
                    [
                        flag
                        for flag in opportunity.evidence.risk_flags
                        if flag != "likely_closed"
                    ]
                    + ["needs_live_verification"]
                )
            )
            opportunity.next_action = next_action_for_opportunity(opportunity)
            con.execute(
                """
                UPDATE opportunities
                SET status = ?, data_json = ?, updated_at = ?
                WHERE opportunity_id = ? AND user_id = ?
                """,
                (
                    opportunity.status.value,
                    json.dumps(
                        opportunity.to_json_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now,
                    opportunity.opportunity_id,
                    _uid(),
                ),
            )
            changed += 1
    return changed
