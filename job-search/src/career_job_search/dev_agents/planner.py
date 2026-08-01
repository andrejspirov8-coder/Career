"""Resource-aware local planner and typed task proposal generation."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from career_job_search.dev_agents.common import (
    DEFAULT_DB_PATH,
    PLANNER_POLICY_VERSION,
    TERMINAL_STATUSES,
    AgentProcessError,
    CoordinatorError,
    CoordinatorPaths,
    SnapshotInfo,
    _json_dump,
    _json_load,
    utc_now_iso,
)
from career_job_search.dev_agents.execution import (
    _finish_run,
    find_agent_policy_rejections,
    run_agent_process,
)
from career_job_search.dev_agents.models import (
    AgentRole,
    AgentTaskSpec,
    LocalAgentSettings,
    PlannerResponse,
)
from career_job_search.dev_agents.proposals import store_planner_proposals
from career_job_search.dev_agents.review import record_model_safety_violation
from career_job_search.dev_agents.runs import (
    _update_run,
    connect,
    create_run,
    init_db,
    list_runs,
)
from career_job_search.dev_agents.snapshots import cleanup_worktree, create_snapshot


def resource_status(
    role: AgentRole, *, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> dict[str, Any]:
    free_bytes = shutil.disk_usage(paths.repo_root).free
    facts: dict[str, Any] = {
        "free_disk_bytes": free_bytes,
        "minimum_free_disk_bytes": settings.resources.min_free_disk_bytes,
        "power_source": "unknown",
        "battery_percent": None,
        "job_automation_active": False,
        "release_check_active": (paths.runtime_root / "release-check.lock").exists(),
    }
    reasons: list[str] = []
    if free_bytes < settings.resources.min_free_disk_bytes:
        reasons.append("less than 20 GB of free disk space is available")

    pmset = shutil.which("pmset")
    if pmset:
        power = subprocess.run(
            [pmset, "-g", "batt"],  # noqa: S603
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        text = f"{power.stdout}\n{power.stderr}"
        if "AC Power" in text:
            facts["power_source"] = "ac"
        elif "Battery Power" in text:
            facts["power_source"] = "battery"
        match = re.search(r"(\d{1,3})%", text)
        if match:
            facts["battery_percent"] = min(int(match.group(1)), 100)

    if (
        role == "implementer"
        and settings.resources.implementer_requires_ac_power
        and facts["power_source"] == "battery"
    ):
        reasons.append("implementation waits until the Mac is connected to power")
    if (
        role == "planner"
        and facts["power_source"] == "battery"
        and isinstance(facts["battery_percent"], int)
        and facts["battery_percent"] < settings.resources.planner_min_battery_percent
    ):
        reasons.append(
            f"planner waits for at least {settings.resources.planner_min_battery_percent}% battery"
        )

    automation_db = paths.repo_root / "state" / "automation.sqlite3"
    if settings.resources.defer_during_job_automation and automation_db.exists():
        try:
            with sqlite3.connect(
                f"file:{automation_db.resolve()}?mode=ro", uri=True, timeout=2
            ) as con:
                row = con.execute(
                    """
                    SELECT COUNT(*) FROM automation_runs
                    WHERE status IN ('running', 'cancel_requested')
                    """
                ).fetchone()
            facts["job_automation_active"] = bool(row and int(row[0]))
        except sqlite3.Error:
            facts["job_automation_active"] = False
    if facts["job_automation_active"]:
        reasons.append("job-search automation is currently running")
    if facts["release_check_active"]:
        reasons.append("the release verification gate is currently running")
    return {
        "ok": not reasons,
        "reason": "; ".join(reasons),
        "facts": facts,
    }


def _planner_evidence(paths: CoordinatorPaths) -> dict[str, Any]:
    failed_runs = [
        {
            "task_id": run["task_id"],
            "phase": run["phase"],
            "error": str(run["error"])[:400],
            "objective": str(run.get("task", {}).get("objective") or "")[:300],
        }
        for run in list_runs(db_path=paths.db_path, limit=30)
        if run["status"] in {"blocked", "failed", "timed_out", "stale"}
    ][:8]
    markers: list[str] = []
    rg = shutil.which("rg")
    if rg:
        process = subprocess.run(
            [  # noqa: S603
                rg,
                "-n",
                "TODO|FIXME|XXX",
                "tools",
                "tests",
                "dashboard",
                "raycast-job-search-hub/src",
                "docs",
            ],
            cwd=paths.repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        markers = process.stdout.splitlines()[:30]
    return {"recent_failed_runs": failed_runs, "repository_markers": markers}


def build_planner_prompt(
    *, settings: LocalAgentSettings, evidence: dict[str, Any]
) -> str:
    payload = {
        "instructions": [
            "You are a fully local read-only development planner in a disposable repository snapshot.",
            "Do not edit files, run tests or builds, access the network, install packages, or use Git history operations.",
            "Inspect no more than twelve relevant files and keep command output small.",
            "Propose only work supported by concrete file, test, type, lint, or documentation evidence.",
            "Do not propose authentication, privacy, secrets, database migrations, dependencies, lockfiles, deployment, Git operations, security policy, agent policy, CV personal content, or live job-search/LinkedIn behavior.",
            "Every proposal must stay within the supplied scan paths and be small enough for one isolated implementation task.",
            "Documentation and test proposals must select a deterministic python, dashboard, or raycast check preset; do not use none for them.",
            "Return at most five proposals. Prefer tests and documentation, then reproducible bounded fixes.",
            "Return only one JSON object matching career_local_dev_planner_response_v1.",
        ],
        "allowed_scan_paths": settings.planner.scan_paths,
        "check_presets": ["none", "python", "dashboard", "raycast"],
        "proposal_fields": {
            "objective": "10-2000 characters",
            "category": [
                "documentation",
                "tests",
                "investigation",
                "bounded_fix",
                "small_change",
                "refactor",
            ],
            "evidence": ["specific path and concrete reason"],
            "allowed_paths": ["repository-relative path"],
            "check_preset": "one fixed preset",
            "risk": ["low", "medium"],
            "priority": ["high", "medium", "low"],
            "estimated_files": "1-8",
            "estimated_diff_lines": "1-600",
        },
        "coordinator_evidence": evidence,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _planner_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema": "career_local_dev_planner_run_v1",
        "planner_run_id": str(row["planner_run_id"]),
        "task_id": str(row["task_id"]),
        "trigger_source": str(row["trigger_source"]),
        "scheduled_for": row["scheduled_for"],
        "status": str(row["status"]),
        "model": str(row["model"]),
        "model_digest": str(row["model_digest"]),
        "started_at": str(row["started_at"]),
        "finished_at": row["finished_at"],
        "result": _json_load(str(row["result_json"]), {}),
        "error": str(row["error"]),
    }


def list_planner_runs(
    *, db_path: Path | str = DEFAULT_DB_PATH, limit: int = 20
) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT * FROM local_agent_planner_runs
            ORDER BY started_at DESC LIMIT ?
            """,
            (min(max(int(limit), 1), 100),),
        ).fetchall()
    return [_planner_row_to_dict(row) for row in rows]


def run_planner(
    *,
    trigger_source: str,
    scheduled_for: str | None,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    if trigger_source not in {"manual", "scheduled", "schedule_catch_up"}:
        raise CoordinatorError("Unsupported planner trigger source.")
    resources = resource_status("planner", settings=settings, paths=paths)
    if not resources["ok"]:
        raise CoordinatorError(f"Planner deferred: {resources['reason']}")
    if scheduled_for:
        with connect(paths.db_path) as con:
            existing = con.execute(
                "SELECT * FROM local_agent_planner_runs WHERE scheduled_for = ?",
                (scheduled_for,),
            ).fetchone()
        if existing:
            return _planner_row_to_dict(existing)

    task = AgentTaskSpec(
        objective=(
            "Inspect approved development surfaces and propose up to five bounded, "
            "evidence-backed local development tasks. Do not modify files."
        ),
        role="planner",
        allowed_paths=settings.planner.scan_paths,
        risk="low",
        context_notes=f"Planner policy: {PLANNER_POLICY_VERSION}",
        timeout_seconds=settings.roles["planner"].timeout_seconds,
    )
    run = create_run(task, settings=settings, paths=paths)
    task_id = run["task_id"]
    planner_run_id = f"planner_{uuid4().hex}"
    model = settings.roles["planner"].model
    digest = settings.models[model].digest
    started_at = utc_now_iso()
    with connect(paths.db_path) as con:
        con.execute(
            """
            INSERT INTO local_agent_planner_runs(
              planner_run_id, task_id, trigger_source, scheduled_for, status,
              model, model_digest, started_at
            ) VALUES (?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                planner_run_id,
                task_id,
                trigger_source,
                scheduled_for,
                model,
                digest,
                started_at,
            ),
        )
    snapshot: SnapshotInfo | None = None
    try:
        _update_run(
            task_id,
            db_path=paths.db_path,
            status="snapshotting",
            phase="planner_snapshot",
            started_at=started_at,
            model=model,
            model_digest=digest,
        )
        snapshot = create_snapshot(task_id, settings=settings, paths=paths)
        run_dir = paths.runtime_root / "runs" / task_id
        _update_run(
            task_id,
            db_path=paths.db_path,
            status="running",
            phase="planner",
            snapshot_commit=snapshot.commit,
            worktree_path=str(snapshot.worktree),
            safety_json=_json_dump(
                {
                    "offline_only": True,
                    "active_workspace_writable": False,
                    "excluded_snapshot_paths": list(snapshot.excluded_paths),
                    "git_history_mutations_allowed": False,
                    "planner_policy": PLANNER_POLICY_VERSION,
                }
            ),
        )
        response = run_agent_process(
            task_id=task_id,
            role="planner",
            model=model,
            label="planner-1",
            prompt=build_planner_prompt(
                settings=settings, evidence=_planner_evidence(paths)
            ),
            worktree=snapshot.worktree,
            run_dir=run_dir,
            timeout_seconds=settings.roles["planner"].timeout_seconds,
            settings=settings,
            paths=paths,
            response_model=PlannerResponse,
        )
        policy_rejections = find_agent_policy_rejections(run_dir)
        if policy_rejections:
            record_model_safety_violation(
                model,
                digest,
                privacy=False,
                reason="The local planner attempted a forbidden command.",
                settings=settings,
                paths=paths,
            )
            raise CoordinatorError(
                "The local planner attempted a forbidden command and produced no proposals."
            )
        if response.status == "blocked":
            raise CoordinatorError(
                response.blocking_reason or "The local planner reported a blocker."
            )
        stored = store_planner_proposals(
            planner_run_id,
            response.proposals,
            settings=settings,
            paths=paths,
        )
        payload = {
            **response.model_dump(mode="json"),
            "stored_proposal_ids": [item["proposal_id"] for item in stored],
            "stored_count": len(stored),
            "resource_status": resources,
        }
        finished_at = utc_now_iso()
        with connect(paths.db_path) as con:
            con.execute(
                """
                UPDATE local_agent_planner_runs
                SET status = 'completed', finished_at = ?, result_json = ?
                WHERE planner_run_id = ?
                """,
                (finished_at, _json_dump(payload), planner_run_id),
            )
        _finish_run(
            task_id,
            status="ready_for_codex_review",
            phase="planner_completed",
            paths=paths,
            result_json=_json_dump(payload),
        )
    except (AgentProcessError, CoordinatorError, OSError, ValidationError) as exc:
        finished_at = utc_now_iso()
        status = exc.status if isinstance(exc, AgentProcessError) else "failed"
        with connect(paths.db_path) as con:
            con.execute(
                """
                UPDATE local_agent_planner_runs
                SET status = ?, finished_at = ?, error = ?
                WHERE planner_run_id = ?
                """,
                (status, finished_at, str(exc), planner_run_id),
            )
        _finish_run(
            task_id,
            status=status if status in TERMINAL_STATUSES else "failed",
            phase="planner_failed",
            paths=paths,
            error=str(exc),
        )
    finally:
        if snapshot and snapshot.worktree.exists():
            cleanup_worktree(snapshot.worktree, paths=paths, force=True)
    with connect(paths.db_path) as con:
        row = con.execute(
            "SELECT * FROM local_agent_planner_runs WHERE planner_run_id = ?",
            (planner_run_id,),
        ).fetchone()
    if row is None:
        raise CoordinatorError("Planner run disappeared.")
    return _planner_row_to_dict(row)
