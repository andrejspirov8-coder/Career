"""SQLite run storage for local development agents."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from career_job_search.dev_agents.common import (
    ACTIVE_STATUSES,
    DEFAULT_DB_PATH,
    MAX_PATCH_PREVIEW_CHARS,
    PLANNER_RUN_ID_PATTERN,
    PROPOSAL_ID_PATTERN,
    SCHEMA_SQL,
    TASK_ID_PATTERN,
    CoordinatorError,
    CoordinatorPaths,
    _json_load,
    utc_now_iso,
)
from career_job_search.dev_agents.models import AgentTaskSpec, LocalAgentSettings
from career_job_search.dev_agents.policy import validate_task_policy

SCHEMA_VERSION = 1

_SCHEMA_META_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_meta "
    "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
)


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return con


def _ensure_column(
    con: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    existing = {
        str(row["name"])
        for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    settings: LocalAgentSettings | None = None,
) -> Path:
    path = Path(db_path)
    required = settings.limits.required_safe_runs if settings else 10
    now = utc_now_iso()
    with connect(path) as con:
        con.executescript(SCHEMA_SQL)
        con.execute(_SCHEMA_META_SQL)
        con.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        for column, definition in (
            ("model_digest", "TEXT"),
            ("proposal_id", "TEXT"),
            ("secondary_review_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("first_pass_ok", "INTEGER NOT NULL DEFAULT 0"),
            ("approval_policy", "TEXT"),
            ("auto_apply_receipt_json", "TEXT NOT NULL DEFAULT '{}'"),
        ):
            _ensure_column(con, "local_agent_runs", column, definition)
        _ensure_column(
            con, "local_agent_settings", "selected_implementer_digest", "TEXT"
        )
        con.execute(
            """
            INSERT OR IGNORE INTO local_agent_settings(
              id, safe_applied_runs, local_first_enabled, updated_at
            ) VALUES (1, 0, 0, ?)
            """,
            (now,),
        )
        con.execute(
            """
            INSERT OR IGNORE INTO local_agent_autonomy(
              id, tier, auto_apply_enabled, manually_paused, updated_at
            ) VALUES (1, 0, 0, 0, ?)
            """,
            (now,),
        )
        con.execute(
            """
            INSERT OR IGNORE INTO local_agent_service(id, status, updated_at)
            VALUES (1, 'stopped', ?)
            """,
            (now,),
        )
        con.execute(
            """
            UPDATE local_agent_settings
            SET local_first_enabled = CASE
              WHEN safe_applied_runs >= ? THEN 1 ELSE local_first_enabled END
            WHERE id = 1
            """,
            (required,),
        )
        model_state_count = int(
            con.execute(
                "SELECT COUNT(*) FROM local_agent_model_qualifications"
            ).fetchone()[0]
        )
        if model_state_count == 0 and settings is not None:
            legacy = con.execute(
                "SELECT * FROM local_agent_settings WHERE id = 1"
            ).fetchone()
            legacy_model = str(legacy["selected_implementer_model"] or "")
            if legacy_model in settings.models:
                digest = settings.models[legacy_model].digest
                qualified_at = legacy["qualified_at"]
                safe_runs = int(legacy["safe_applied_runs"])
                con.execute(
                    """
                    INSERT INTO local_agent_model_qualifications(
                      model_tag, model_digest, qualified, qualified_at,
                      qualification_json, safe_applied_runs, safe_apply_streak,
                      total_applied_runs, first_pass_applied_runs, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        legacy_model,
                        digest,
                        1 if qualified_at else 0,
                        qualified_at,
                        str(legacy["qualification_json"]),
                        safe_runs,
                        safe_runs,
                        safe_runs,
                        safe_runs,
                        now,
                    ),
                )
                con.execute(
                    """
                    UPDATE local_agent_settings
                    SET selected_implementer_digest = ?, updated_at = ?
                    WHERE id = 1
                    """,
                    (digest, now),
                )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def validate_task_id(task_id: str) -> str:
    clean = task_id.strip()
    if not TASK_ID_PATTERN.fullmatch(clean):
        raise CoordinatorError("Invalid local-agent task id.")
    return clean


def validate_proposal_id(proposal_id: str) -> str:
    clean = proposal_id.strip()
    if not PROPOSAL_ID_PATTERN.fullmatch(clean):
        raise CoordinatorError("Invalid local-agent proposal id.")
    return clean


def validate_planner_run_id(planner_run_id: str) -> str:
    clean = planner_run_id.strip()
    if not PLANNER_RUN_ID_PATTERN.fullmatch(clean):
        raise CoordinatorError("Invalid local-agent planner run id.")
    return clean


def _row_to_run(row: sqlite3.Row, *, include_streams: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": "career_local_dev_agent_result_v1",
        "task_id": str(row["task_id"]),
        "status": str(row["status"]),
        "phase": str(row["phase"]),
        "role": str(row["role"]),
        "model": str(row["model"]),
        "model_digest": row["model_digest"],
        "proposal_id": row["proposal_id"],
        "task": _json_load(str(row["task_json"]), {}),
        "created_at": str(row["created_at"]),
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "snapshot_commit": row["snapshot_commit"],
        "worktree_path": row["worktree_path"],
        "patch_path": row["patch_path"],
        "patch_sha256": row["patch_sha256"],
        "reviewed_patch_sha256": row["reviewed_patch_sha256"],
        "reviewed_by": row["reviewed_by"],
        "reviewed_at": row["reviewed_at"],
        "attempt": int(row["attempt"]),
        "cancel_requested": bool(row["cancel_requested"]),
        "result": _json_load(str(row["result_json"]), {}),
        "local_review": _json_load(str(row["local_review_json"]), {}),
        "secondary_review": _json_load(str(row["secondary_review_json"]), {}),
        "verification": _json_load(str(row["verification_json"]), []),
        "post_apply_verification": _json_load(
            str(row["post_apply_verification_json"]), []
        ),
        "first_pass_ok": bool(row["first_pass_ok"]),
        "approval_policy": row["approval_policy"],
        "auto_apply_receipt": _json_load(str(row["auto_apply_receipt_json"]), {}),
        "error": str(row["error"]),
        "safety": _json_load(str(row["safety_json"]), {}),
    }
    if include_streams:
        run_dir = Path(str(row["run_dir"]))
        data["artifacts"] = {
            "run_dir": str(run_dir),
            "stdout_files": [
                str(path) for path in sorted(run_dir.glob("*/stdout.jsonl"))
            ],
            "stderr_files": [
                str(path) for path in sorted(run_dir.glob("*/stderr.log"))
            ],
        }
        patch_value = row["patch_path"]
        if patch_value:
            patch_path = Path(str(patch_value))
            try:
                preview_allowed = patch_path.resolve().is_relative_to(run_dir.resolve())
            except OSError:
                preview_allowed = False
            if preview_allowed and patch_path.is_file():
                patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
                data["patch_preview"] = patch_text[:MAX_PATCH_PREVIEW_CHARS]
                data["patch_preview_truncated"] = (
                    len(patch_text) > MAX_PATCH_PREVIEW_CHARS
                )
    return data


def get_run(
    task_id: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    include_streams: bool = True,
) -> dict[str, Any] | None:
    clean = validate_task_id(task_id)
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM local_agent_runs WHERE task_id = ?", (clean,)
        ).fetchone()
    return _row_to_run(row, include_streams=include_streams) if row else None


def list_runs(
    *, db_path: Path | str = DEFAULT_DB_PATH, limit: int = 30
) -> list[dict[str, Any]]:
    init_db(db_path)
    safe_limit = min(max(int(limit), 1), 100)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT * FROM local_agent_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [_row_to_run(row) for row in rows]


def _update_run(
    task_id: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    **values: Any,
) -> None:
    clean = validate_task_id(task_id)
    if not values:
        return
    allowed = {
        "status",
        "phase",
        "model",
        "model_digest",
        "proposal_id",
        "started_at",
        "finished_at",
        "snapshot_commit",
        "worktree_path",
        "patch_path",
        "patch_sha256",
        "reviewed_patch_sha256",
        "reviewed_by",
        "reviewed_at",
        "child_pid",
        "attempt",
        "cancel_requested",
        "result_json",
        "local_review_json",
        "secondary_review_json",
        "verification_json",
        "post_apply_verification_json",
        "first_pass_ok",
        "approval_policy",
        "auto_apply_receipt_json",
        "error",
        "safety_json",
    }
    unknown = set(values) - allowed
    if unknown:
        raise CoordinatorError(f"Unsupported run fields: {sorted(unknown)}")
    assignments = ", ".join(f"{key} = ?" for key in values)
    with connect(db_path) as con:
        con.execute(
            f"UPDATE local_agent_runs SET {assignments} WHERE task_id = ?",  # noqa: S608 - keys are allow-listed above
            (*values.values(), clean),
        )
        if "status" in values:
            row = con.execute(
                "SELECT proposal_id FROM local_agent_runs WHERE task_id = ?",
                (clean,),
            ).fetchone()
            proposal_id = str(row["proposal_id"] or "") if row else ""
            status = str(values["status"])
            proposal_status = (
                "queued"
                if status == "queued"
                else "running"
                if status in ACTIVE_STATUSES
                or status in {"ready_for_codex_review", "approved"}
                else "applied"
                if status == "applied"
                else "rejected"
                if status == "rejected"
                else "cancelled"
                if status == "cancelled"
                else "blocked"
                if status in {"blocked", "failed", "timed_out", "stale"}
                else None
            )
            if proposal_id and proposal_status:
                con.execute(
                    """
                    UPDATE local_agent_proposals
                    SET status = ?, updated_at = ?
                    WHERE proposal_id = ?
                    """,
                    (proposal_status, utc_now_iso(), proposal_id),
                )


def create_run(
    task: AgentTaskSpec,
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    validate_task_policy(task, settings=settings)
    if proposal_id is not None:
        proposal_id = validate_proposal_id(proposal_id)
    task_id = f"agent_{uuid4().hex}"
    run_dir = paths.runtime_root / "runs" / task_id
    run_dir.mkdir(parents=True, exist_ok=False)
    run_dir.chmod(0o700)
    model = settings.roles[task.role].model
    model_digest = settings.models[model].digest
    now = utc_now_iso()
    init_db(paths.db_path, settings=settings)
    with connect(paths.db_path) as con:
        con.execute(
            """
            INSERT INTO local_agent_runs(
              task_id, status, phase, role, model, model_digest, proposal_id,
              task_json, created_at, run_dir
            ) VALUES (?, 'queued', 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task.role,
                model,
                model_digest,
                proposal_id,
                task.model_dump_json(),
                now,
                str(run_dir),
            ),
        )
    result = get_run(task_id, db_path=paths.db_path)
    if result is None:
        raise CoordinatorError("Failed to create local-agent run.")
    return result


def get_rollout(
    *, settings: LocalAgentSettings, db_path: Path | str = DEFAULT_DB_PATH
) -> dict[str, Any]:
    init_db(db_path, settings=settings)
    with connect(db_path) as con:
        legacy = con.execute(
            "SELECT * FROM local_agent_settings WHERE id = 1"
        ).fetchone()
        model_rows = con.execute(
            """
            SELECT * FROM local_agent_model_qualifications
            ORDER BY updated_at DESC, model_tag ASC
            """
        ).fetchall()
        autonomy_row = con.execute(
            "SELECT * FROM local_agent_autonomy WHERE id = 1"
        ).fetchone()
    if legacy is None:
        raise CoordinatorError("Local-agent rollout state is unavailable.")
    selected_model = str(legacy["selected_implementer_model"] or "") or None
    selected_digest = str(legacy["selected_implementer_digest"] or "") or None
    selected_state = next(
        (
            row
            for row in model_rows
            if row["model_tag"] == selected_model
            and row["model_digest"] == selected_digest
        ),
        None,
    )
    safe_runs = int(selected_state["safe_applied_runs"]) if selected_state else 0
    total_runs = int(selected_state["total_applied_runs"]) if selected_state else 0
    first_pass_runs = (
        int(selected_state["first_pass_applied_runs"]) if selected_state else 0
    )
    required = settings.autonomy.tier_one_safe_runs
    model_states = [
        {
            "model": str(row["model_tag"]),
            "digest": str(row["model_digest"]),
            "qualified": bool(row["qualified"]),
            "qualified_at": row["qualified_at"],
            "safe_applied_runs": int(row["safe_applied_runs"]),
            "safe_apply_streak": int(row["safe_apply_streak"]),
            "total_applied_runs": int(row["total_applied_runs"]),
            "first_pass_applied_runs": int(row["first_pass_applied_runs"]),
            "first_pass_rate": round(
                int(row["first_pass_applied_runs"])
                / max(int(row["total_applied_runs"]), 1),
                3,
            ),
            "scope_violations": int(row["scope_violations"]),
            "privacy_violations": int(row["privacy_violations"]),
            "qualification": _json_load(str(row["qualification_json"]), {}),
            "updated_at": str(row["updated_at"]),
        }
        for row in model_rows
    ]
    autonomy = {
        "tier": int(autonomy_row["tier"]) if autonomy_row else 0,
        "auto_apply_enabled": bool(autonomy_row["auto_apply_enabled"])
        if autonomy_row
        else False,
        "manually_paused": bool(autonomy_row["manually_paused"])
        if autonomy_row
        else False,
        "paused_reason": str(autonomy_row["paused_reason"]) if autonomy_row else "",
        "last_evaluated_at": autonomy_row["last_evaluated_at"]
        if autonomy_row
        else None,
    }
    return {
        "safe_applied_runs": safe_runs,
        "safe_apply_streak": int(selected_state["safe_apply_streak"])
        if selected_state
        else 0,
        "total_applied_runs": total_runs,
        "first_pass_applied_runs": first_pass_runs,
        "first_pass_rate": round(first_pass_runs / max(total_runs, 1), 3),
        "required_safe_runs": required,
        "remaining_safe_runs": max(required - safe_runs, 0),
        "local_first_enabled": bool(
            selected_state
            and selected_state["qualified"]
            and safe_runs >= settings.autonomy.tier_one_safe_runs
        ),
        "qualified_at": selected_state["qualified_at"] if selected_state else None,
        "selected_implementer_model": selected_model,
        "selected_implementer_digest": selected_digest,
        "qualification": _json_load(str(selected_state["qualification_json"]), {})
        if selected_state
        else {},
        "models": model_states,
        "autonomy": autonomy,
        "updated_at": str(legacy["updated_at"]),
    }
