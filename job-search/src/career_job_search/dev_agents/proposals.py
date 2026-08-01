"""Planner proposal storage and approval rules for local agents."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from career_job_search.dev_agents.common import (
    DEFAULT_DB_PATH,
    SENSITIVE_OBJECTIVE_TERMS,
    CoordinatorError,
    CoordinatorPaths,
    _json_dump,
    _json_load,
    utc_now_iso,
)
from career_job_search.dev_agents.models import (
    AgentTaskSpec,
    LocalAgentSettings,
    PlannerProposalDraft,
    VerificationCheck,
)
from career_job_search.dev_agents.policy import (
    is_snapshot_forbidden,
    is_write_forbidden,
    path_is_allowed,
    validate_task_policy,
)
from career_job_search.dev_agents.runs import (
    connect,
    get_run,
    init_db,
    validate_planner_run_id,
    validate_proposal_id,
)


def _proposal_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema": "career_local_dev_proposal_v1",
        "proposal_id": str(row["proposal_id"]),
        "planner_run_id": str(row["planner_run_id"]),
        "fingerprint": str(row["fingerprint"]),
        "status": str(row["status"]),
        "category": str(row["category"]),
        "objective": str(row["objective"]),
        "evidence": _json_load(str(row["evidence_json"]), []),
        "allowed_paths": _json_load(str(row["allowed_paths_json"]), []),
        "check_preset": str(row["check_preset"]),
        "risk": str(row["risk"]),
        "priority": str(row["priority"]),
        "estimated_files": int(row["estimated_files"]),
        "estimated_diff_lines": int(row["estimated_diff_lines"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "approved_at": row["approved_at"],
        "rejected_at": row["rejected_at"],
        "task_id": row["task_id"],
    }


def list_proposals(
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db(db_path)
    safe_limit = min(max(int(limit), 1), 100)
    query = "SELECT * FROM local_agent_proposals"
    parameters: list[Any] = []
    if status:
        query += " WHERE status = ?"
        parameters.append(status)
    query += (
        " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
        "created_at DESC LIMIT ?"
    )
    parameters.append(safe_limit)
    with connect(db_path) as con:
        rows = con.execute(query, parameters).fetchall()
    return [_proposal_row_to_dict(row) for row in rows]


def get_proposal(
    proposal_id: str, *, db_path: Path | str = DEFAULT_DB_PATH
) -> dict[str, Any] | None:
    clean = validate_proposal_id(proposal_id)
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM local_agent_proposals WHERE proposal_id = ?", (clean,)
        ).fetchone()
    return _proposal_row_to_dict(row) if row else None


def _proposal_fingerprint(proposal: PlannerProposalDraft) -> str:
    payload = {
        "objective": " ".join(proposal.objective.casefold().split()),
        "allowed_paths": sorted(proposal.allowed_paths),
        "category": proposal.category,
    }
    return hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()


def _validate_proposal_policy(
    proposal: PlannerProposalDraft, *, settings: LocalAgentSettings
) -> None:
    objective = proposal.objective.casefold()
    if any(term in objective for term in SENSITIVE_OBJECTIVE_TERMS):
        raise CoordinatorError(
            "Planner proposals cannot include sensitive Main-Codex-only work."
        )
    if proposal.estimated_files > settings.limits.max_changed_files:
        raise CoordinatorError("Planner proposal exceeds the changed-file limit.")
    if proposal.estimated_diff_lines > settings.limits.max_diff_lines:
        raise CoordinatorError("Planner proposal exceeds the diff-line limit.")
    scan_paths = settings.planner.scan_paths
    for path in proposal.allowed_paths:
        if not path_is_allowed(path, scan_paths):
            raise CoordinatorError(
                f"Planner proposal leaves approved scan paths: {path}"
            )
        if is_snapshot_forbidden(path, settings) or is_write_forbidden(path):
            raise CoordinatorError(f"Planner proposal targets a protected path: {path}")


def store_planner_proposals(
    planner_run_id: str,
    proposals: Sequence[PlannerProposalDraft],
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> list[dict[str, Any]]:
    clean_run_id = validate_planner_run_id(planner_run_id)
    stored: list[dict[str, Any]] = []
    now = utc_now_iso()
    for proposal in proposals[: settings.planner.max_proposals_per_run]:
        try:
            _validate_proposal_policy(proposal, settings=settings)
        except CoordinatorError:
            continue
        fingerprint = _proposal_fingerprint(proposal)
        with connect(paths.db_path) as con:
            duplicate = con.execute(
                """
                SELECT proposal_id FROM local_agent_proposals
                WHERE fingerprint = ?
                  AND status IN ('proposed', 'approved', 'queued', 'running')
                LIMIT 1
                """,
                (fingerprint,),
            ).fetchone()
            if duplicate:
                continue
            proposal_id = f"proposal_{uuid4().hex}"
            con.execute(
                """
                INSERT INTO local_agent_proposals(
                  proposal_id, planner_run_id, fingerprint, status, category,
                  objective, evidence_json, allowed_paths_json, check_preset,
                  risk, priority, estimated_files, estimated_diff_lines,
                  created_at, updated_at
                ) VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    clean_run_id,
                    fingerprint,
                    proposal.category,
                    proposal.objective,
                    _json_dump(proposal.evidence),
                    _json_dump(proposal.allowed_paths),
                    proposal.check_preset,
                    proposal.risk,
                    proposal.priority,
                    proposal.estimated_files,
                    proposal.estimated_diff_lines,
                    now,
                    now,
                ),
            )
        stored_item = get_proposal(proposal_id, db_path=paths.db_path)
        if stored_item:
            stored.append(stored_item)
    return stored


def verification_checks_for_preset(preset: str) -> list[VerificationCheck]:
    if preset == "none":
        return []
    if preset == "python":
        return [
            VerificationCheck(
                name="Python tests",
                argv=["python", "-m", "pytest", "-q"],
                timeout_seconds=1800,
            )
        ]
    if preset == "dashboard":
        return [
            VerificationCheck(
                name="Dashboard tests",
                argv=["npm", "test"],
                cwd="dashboard",
                timeout_seconds=900,
            ),
            VerificationCheck(
                name="Dashboard typecheck",
                argv=["npm", "run", "typecheck"],
                cwd="dashboard",
                timeout_seconds=900,
            ),
        ]
    if preset == "architecture":
        return [
            VerificationCheck(
                name="Architecture: import boundaries",
                argv=["python", "-m", "career_job_search.dev_agents.architecture", "check"],
                timeout_seconds=300,
            ),
            VerificationCheck(
                name="Architecture: circular imports",
                argv=["python", "-m", "career_job_search.dev_agents.architecture", "cycles"],
                timeout_seconds=300,
            ),
        ]
    raise CoordinatorError("Unsupported proposal verification preset.")


def _local_date(now: datetime, timezone_name: str) -> str:
    return now.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def approve_proposal(
    proposal_id: str,
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
    objective: str | None = None,
    allowed_paths: Sequence[str] | None = None,
    check_preset: str | None = None,
) -> dict[str, Any]:
    proposal = get_proposal(proposal_id, db_path=paths.db_path)
    if proposal is None:
        raise CoordinatorError("Local-agent proposal was not found.")
    if proposal["status"] != "proposed":
        raise CoordinatorError("Only a proposed task can be approved.")
    updated = PlannerProposalDraft(
        objective=(objective or proposal["objective"]).strip(),
        category=proposal["category"],
        evidence=proposal["evidence"],
        allowed_paths=list(allowed_paths or proposal["allowed_paths"]),
        check_preset=check_preset or proposal["check_preset"],
        risk=proposal["risk"],
        priority=proposal["priority"],
        estimated_files=proposal["estimated_files"],
        estimated_diff_lines=proposal["estimated_diff_lines"],
    )
    _validate_proposal_policy(updated, settings=settings)
    checks = verification_checks_for_preset(updated.check_preset)
    if updated.category in {"documentation", "tests"} and not checks:
        raise CoordinatorError(
            "Documentation and test proposals require a deterministic check before approval."
        )
    task = AgentTaskSpec(
        objective=updated.objective,
        role="implementer",
        allowed_paths=updated.allowed_paths,
        acceptance_checks=checks,
        risk=updated.risk,
        context_notes=(
            f"Approved planner proposal {proposal_id}. Evidence: "
            + " | ".join(updated.evidence)
        )[:8000],
        max_changed_files=min(updated.estimated_files, 8),
        max_diff_lines=min(updated.estimated_diff_lines, 600),
        timeout_seconds=settings.roles["implementer"].timeout_seconds,
    )
    validate_task_policy(task, settings=settings)
    task_id = f"agent_{uuid4().hex}"
    run_dir = paths.runtime_root / "runs" / task_id
    run_dir.mkdir(parents=True, exist_ok=False)
    run_dir.chmod(0o700)
    model = settings.roles[task.role].model
    model_digest = settings.models[model].digest
    now = utc_now_iso()
    today = _local_date(datetime.now(UTC), settings.planner.timezone)
    committed = False
    try:
        init_db(paths.db_path, settings=settings)
        with connect(paths.db_path) as con:
            con.execute("BEGIN IMMEDIATE")
            current = con.execute(
                "SELECT status FROM local_agent_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if current is None:
                raise CoordinatorError("Local-agent proposal was not found.")
            if str(current["status"]) != "proposed":
                raise CoordinatorError("Only a proposed task can be approved.")
            approved_rows = con.execute(
                """
                SELECT approved_at FROM local_agent_proposals
                WHERE approved_at IS NOT NULL
                """
            ).fetchall()
            approved_today = sum(
                1
                for row in approved_rows
                if _local_date(
                    datetime.fromisoformat(str(row["approved_at"])),
                    settings.planner.timezone,
                )
                == today
            )
            if approved_today >= settings.planner.max_approved_implementations_per_day:
                raise CoordinatorError(
                    "The daily limit of two approved local implementations has been reached."
                )
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
            changed = con.execute(
                """
                UPDATE local_agent_proposals
                SET status = 'queued', objective = ?, allowed_paths_json = ?,
                    check_preset = ?, approved_at = ?, updated_at = ?, task_id = ?
                WHERE proposal_id = ? AND status = 'proposed'
                """,
                (
                    updated.objective,
                    _json_dump(updated.allowed_paths),
                    updated.check_preset,
                    now,
                    now,
                    task_id,
                    proposal_id,
                ),
            )
            if changed.rowcount != 1:
                raise CoordinatorError("Proposal approval changed concurrently.")
        committed = True
    finally:
        if not committed and run_dir.exists():
            try:
                run_dir.rmdir()
            except OSError:
                pass
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Approved local-agent run disappeared.")
    result = get_proposal(proposal_id, db_path=paths.db_path)
    if result is None:
        raise CoordinatorError("Approved proposal disappeared.")
    return {"proposal": result, "run": run}


def reject_proposal(proposal_id: str, *, paths: CoordinatorPaths) -> dict[str, Any]:
    proposal = get_proposal(proposal_id, db_path=paths.db_path)
    if proposal is None:
        raise CoordinatorError("Local-agent proposal was not found.")
    if proposal["status"] != "proposed":
        raise CoordinatorError("Only an unqueued proposal can be rejected.")
    now = utc_now_iso()
    with connect(paths.db_path) as con:
        con.execute(
            """
            UPDATE local_agent_proposals
            SET status = 'rejected', rejected_at = ?, updated_at = ?
            WHERE proposal_id = ?
            """,
            (now, now, proposal_id),
        )
    result = get_proposal(proposal_id, db_path=paths.db_path)
    if result is None:
        raise CoordinatorError("Rejected proposal disappeared.")
    return result
