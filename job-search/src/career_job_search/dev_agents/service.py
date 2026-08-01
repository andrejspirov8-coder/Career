"""Dashboard overview, scheduler service, worker, and retention cleanup."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from career_job_search.dev_agents.common import (
    ACTIVE_STATUSES,
    CoordinatorError,
    CoordinatorPaths,
    utc_now_iso,
)
from career_job_search.dev_agents.models import AgentRole, LocalAgentSettings
from career_job_search.dev_agents.planner import (
    list_planner_runs,
    resource_status,
)
from career_job_search.dev_agents.proposals import list_proposals
from career_job_search.dev_agents.review import evaluate_autonomy
from career_job_search.dev_agents.run_flow import execute_run
from career_job_search.dev_agents.runs import connect, get_rollout, init_db, list_runs
from career_job_search.dev_agents.snapshots import cleanup_worktree


def build_overview(
    *, settings: LocalAgentSettings, paths: CoordinatorPaths, limit: int = 30
) -> dict[str, Any]:
    runs = list_runs(db_path=paths.db_path, limit=limit)
    counts: dict[str, int] = {}
    proposal_counts: dict[str, int] = {}
    with connect(paths.db_path) as con:
        for row in con.execute(
            "SELECT status, COUNT(*) AS count FROM local_agent_runs GROUP BY status"
        ).fetchall():
            counts[str(row["status"])] = int(row["count"])
        for row in con.execute(
            "SELECT status, COUNT(*) AS count FROM local_agent_proposals GROUP BY status"
        ).fetchall():
            proposal_counts[str(row["status"])] = int(row["count"])
    autonomy = evaluate_autonomy(settings=settings, paths=paths)
    return {
        "schema": "career_local_dev_agent_overview_v1",
        "generated_at": utc_now_iso(),
        "counts": counts,
        "active_runs": [run for run in runs if run["status"] in ACTIVE_STATUSES],
        "recent_runs": runs,
        "proposals": list_proposals(db_path=paths.db_path, limit=30),
        "proposal_counts": proposal_counts,
        "planner_runs": list_planner_runs(db_path=paths.db_path, limit=10),
        "rollout": get_rollout(settings=settings, db_path=paths.db_path),
        "autonomy": autonomy,
        "service": get_service_status(settings=settings, paths=paths),
        "resources": {
            "planner": resource_status("planner", settings=settings, paths=paths),
            "implementer": resource_status(
                "implementer", settings=settings, paths=paths
            ),
        },
        "roles": {
            role: {
                "model": role_settings.model,
                "sandbox": role_settings.sandbox,
                "timeout_seconds": role_settings.timeout_seconds,
            }
            for role, role_settings in settings.roles.items()
        },
        "limits": settings.limits.model_dump(mode="json"),
        "safety": {
            "local_only": True,
            "online_fallback": False,
            "active_workspace_writes": False,
            "automatic_commit_or_push": False,
            "auto_apply_scope": "Tier 2 documentation and tests only",
            "message": (
                "Agents run in disposable snapshots. Production code always requires "
                "Main Codex; only qualified Tier 2 documentation/test patches may use "
                "the restricted local policy receipt."
            ),
        },
    }


def _next_planner_at(now: datetime, *, settings: LocalAgentSettings) -> datetime:
    timezone = ZoneInfo(settings.planner.timezone)
    local_now = now.astimezone(timezone)
    hour, minute = (int(part) for part in settings.planner.schedule_time.split(":"))
    for offset in range(0, 8):
        candidate_date = local_now.date() + timedelta(days=offset)
        candidate = datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            hour,
            minute,
            tzinfo=timezone,
        )
        if candidate.weekday() not in settings.planner.weekdays:
            continue
        if candidate > local_now:
            return candidate.astimezone(UTC)
    raise CoordinatorError("Could not determine the next planner schedule.")


def _planner_schedule_due(
    now: datetime, *, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> tuple[str, str] | None:
    init_db(paths.db_path, settings=settings)
    timezone = ZoneInfo(settings.planner.timezone)
    local_now = now.astimezone(timezone)
    if local_now.weekday() not in settings.planner.weekdays:
        return None
    hour, minute = (int(part) for part in settings.planner.schedule_time.split(":"))
    scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now < scheduled:
        return None
    scheduled_for = local_now.date().isoformat()
    with connect(paths.db_path) as con:
        existing = con.execute(
            "SELECT 1 FROM local_agent_planner_runs WHERE scheduled_for = ?",
            (scheduled_for,),
        ).fetchone()
    if existing:
        return None
    trigger = (
        "scheduled"
        if local_now < scheduled + timedelta(minutes=30)
        else "schedule_catch_up"
    )
    return scheduled_for, trigger


def get_service_status(
    *, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> dict[str, Any]:
    init_db(paths.db_path, settings=settings)
    with connect(paths.db_path) as con:
        row = con.execute("SELECT * FROM local_agent_service WHERE id = 1").fetchone()
    if row is None:
        raise CoordinatorError("Development-agent service state is unavailable.")
    heartbeat = row["heartbeat_at"]
    online = False
    if heartbeat:
        try:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(str(heartbeat))
            ).total_seconds()
            online = 0 <= age <= 45 and row["status"] == "running"
        except ValueError:
            online = False
    return {
        "schema": "career_local_dev_agent_service_v1",
        "online": online,
        "pid": row["pid"],
        "status": str(row["status"]),
        "started_at": row["started_at"],
        "heartbeat_at": heartbeat,
        "next_planner_at": row["next_planner_at"]
        or _next_planner_at(datetime.now(UTC), settings=settings).isoformat(),
        "last_planner_at": row["last_planner_at"],
        "last_defer_reason": str(row["last_defer_reason"]),
        "schedule_time": settings.planner.schedule_time,
        "timezone": settings.planner.timezone,
        "daily_implementation_cap": settings.planner.max_approved_implementations_per_day,
    }


def _update_service_status(
    *,
    paths: CoordinatorPaths,
    settings: LocalAgentSettings,
    status: str,
    started_at: str | None,
    last_planner_at: str | None = None,
    defer_reason: str = "",
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    next_planner = _next_planner_at(now, settings=settings).isoformat()
    with connect(paths.db_path) as con:
        con.execute(
            """
            UPDATE local_agent_service
            SET pid = ?, status = ?, started_at = COALESCE(?, started_at),
                heartbeat_at = ?, next_planner_at = ?,
                last_planner_at = COALESCE(?, last_planner_at),
                last_defer_reason = ?, updated_at = ?
            WHERE id = 1
            """,
            (
                os.getpid() if status == "running" else None,
                status,
                started_at,
                now.isoformat(),
                next_planner,
                last_planner_at,
                defer_reason[:1000],
                now.isoformat(),
            ),
        )


def _coordinator_command(paths: CoordinatorPaths, *args: str) -> list[str]:
    return [
        sys.executable,
        str(paths.repo_root / "tools" / "local_dev_agents.py"),
        "--repo-root",
        str(paths.repo_root),
        "--runtime-root",
        str(paths.runtime_root),
        "--db",
        str(paths.db_path),
        "--worktree-root",
        str(paths.worktree_root),
        "--backup-root",
        str(paths.backup_root),
        "--config",
        str(paths.config_path),
        *args,
    ]


def _spawn_service_child(
    command: Sequence[str], *, label: str, paths: CoordinatorPaths
) -> subprocess.Popen[bytes]:
    log_dir = paths.runtime_root / "service-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{label}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.log"
    log = log_path.open("ab")
    try:
        return subprocess.Popen(
            list(command),  # noqa: S603
            cwd=paths.repo_root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log.close()


def _stop_service_child(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=7)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def run_development_agent_service(
    *, poll_seconds: float, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> int:
    init_db(paths.db_path, settings=settings)
    interval = max(1.0, min(float(poll_seconds), 60.0))
    started_at = utc_now_iso()
    child: subprocess.Popen[bytes] | None = None
    child_kind = ""
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    previous_handlers = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    for signum in previous_handlers:
        signal.signal(signum, request_stop)
    try:
        while not stopping:
            now = datetime.now(UTC).replace(microsecond=0)
            if child is not None and child.poll() is not None:
                child = None
                child_kind = ""
            defer_reason = ""
            last_planner_at: str | None = None
            if child is None:
                due = _planner_schedule_due(now, settings=settings, paths=paths)
                if due:
                    scheduled_for, trigger = due
                    resources = resource_status(
                        "planner", settings=settings, paths=paths
                    )
                    if resources["ok"]:
                        child = _spawn_service_child(
                            _coordinator_command(
                                paths,
                                "plan",
                                "--trigger-source",
                                trigger,
                                "--scheduled-for",
                                scheduled_for,
                            ),
                            label="planner",
                            paths=paths,
                        )
                        child_kind = "planner"
                        last_planner_at = now.isoformat()
                    else:
                        defer_reason = str(resources["reason"])
                else:
                    with connect(paths.db_path) as con:
                        queued = con.execute(
                            """
                            SELECT role FROM local_agent_runs
                            WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1
                            """
                        ).fetchone()
                    if queued:
                        role: AgentRole = (
                            "implementer"
                            if queued["role"] == "implementer"
                            else "planner"
                        )
                        resources = resource_status(
                            role, settings=settings, paths=paths
                        )
                        if resources["ok"]:
                            child = _spawn_service_child(
                                _coordinator_command(paths, "worker", "--once"),
                                label="worker",
                                paths=paths,
                            )
                            child_kind = "worker"
                        else:
                            defer_reason = str(resources["reason"])
            _update_service_status(
                paths=paths,
                settings=settings,
                status="running",
                started_at=started_at,
                last_planner_at=last_planner_at,
                defer_reason=(
                    defer_reason
                    or (f"{child_kind} is running" if child is not None else "")
                ),
            )
            time.sleep(interval)
        return 0
    finally:
        _stop_service_child(child)
        _update_service_status(
            paths=paths,
            settings=settings,
            status="stopped",
            started_at=None,
        )
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def claim_next_run(*, paths: CoordinatorPaths) -> str | None:
    init_db(paths.db_path)
    with connect(paths.db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            """
            SELECT task_id FROM local_agent_runs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            con.commit()
            return None
        task_id = str(row["task_id"])
        con.execute(
            """
            UPDATE local_agent_runs
            SET status = 'snapshotting', phase = 'claimed'
            WHERE task_id = ? AND status = 'queued'
            """,
            (task_id,),
        )
        con.commit()
    return task_id


def run_worker(
    *, once: bool, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> list[str]:
    completed: list[str] = []
    while True:
        task_id = claim_next_run(paths=paths)
        if not task_id:
            break
        result = execute_run(task_id, settings=settings, paths=paths)
        completed.append(task_id)
        if once or (
            result["status"] == "queued" and result["phase"] == "resource_deferred"
        ):
            break
    return completed


def spawn_worker(*, paths: CoordinatorPaths) -> int:
    log_dir = paths.runtime_root / "worker-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"worker-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--repo-root",
        str(paths.repo_root),
        "--runtime-root",
        str(paths.runtime_root),
        "--db",
        str(paths.db_path),
        "--worktree-root",
        str(paths.worktree_root),
        "--backup-root",
        str(paths.backup_root),
        "--config",
        str(paths.config_path),
        "worker",
        "--once",
    ]
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,  # noqa: S603
            cwd=paths.repo_root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    return process.pid


def cleanup_old_runs(
    *, older_than_days: int, paths: CoordinatorPaths
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    removable_statuses = {
        "applied",
        "blocked",
        "failed",
        "timed_out",
        "cancelled",
        "stale",
        "rejected",
    }
    removed: list[str] = []
    for run in list_runs(db_path=paths.db_path, limit=100):
        if run["status"] not in removable_statuses or not run.get("finished_at"):
            continue
        finished = datetime.fromisoformat(str(run["finished_at"]))
        if finished > cutoff:
            continue
        worktree_value = run.get("worktree_path")
        if worktree_value and Path(str(worktree_value)).exists():
            cleanup_worktree(Path(str(worktree_value)), paths=paths, force=True)
        run_dir = paths.runtime_root / "runs" / run["task_id"]
        expected_parent = (paths.runtime_root / "runs").resolve()
        if run_dir.resolve(strict=False).parent != expected_parent:
            raise CoordinatorError("Refusing to clean an unexpected run directory.")
        if run_dir.exists():
            shutil.rmtree(run_dir)
        with connect(paths.db_path) as con:
            con.execute(
                "DELETE FROM local_agent_runs WHERE task_id = ?", (run["task_id"],)
            )
        removed.append(run["task_id"])
    return {"removed": removed, "older_than_days": older_than_days}
