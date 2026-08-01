"""Approved patch application, verification, cancellation, and export."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from career_job_search.dev_agents.common import (
    ACTIVE_STATUSES,
    AUTO_APPLY_POLICY_VERSION,
    AgentProcessError,
    CoordinatorError,
    CoordinatorPaths,
    _json_dump,
    utc_now_iso,
)
from career_job_search.dev_agents.execution import (
    _finish_run,
    build_agent_prompt,
    find_agent_policy_rejections,
    run_agent_process,
    run_checks,
)
from career_job_search.dev_agents.models import AgentTaskSpec, LocalAgentSettings
from career_job_search.dev_agents.review import (
    _assert_patch_fresh,
    _record_apply_result,
    approve_run,
    auto_apply_eligibility,
    create_workspace_backup,
    record_model_safety_violation,
    set_autonomy_paused,
)
from career_job_search.dev_agents.runs import _update_run, connect, get_run
from career_job_search.dev_agents.sandbox import _redact_stream
from career_job_search.dev_agents.snapshots import _git, cleanup_worktree


def maybe_auto_apply_run(
    task_id: str,
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Verified run disappeared before autonomy evaluation.")
    preliminary = auto_apply_eligibility(
        run, settings=settings, paths=paths, require_secondary_review=False
    )
    if not preliminary["eligible"]:
        return run
    secondary_model = settings.secondary_reviewer_model
    if secondary_model == run["model"]:
        return run
    with connect(paths.db_path) as con:
        qualified = con.execute(
            """
            SELECT qualified FROM local_agent_model_qualifications
            WHERE model_tag = ? AND model_digest = ?
            """,
            (secondary_model, settings.models[secondary_model].digest),
        ).fetchone()
    if not qualified or not qualified["qualified"]:
        return run
    worktree = Path(str(run.get("worktree_path") or ""))
    patch_path = Path(str(run.get("patch_path") or ""))
    if not worktree.is_dir() or not patch_path.is_file():
        return run
    task = AgentTaskSpec.model_validate(run["task"])
    run_dir = paths.runtime_root / "runs" / task_id
    try:
        review = run_agent_process(
            task_id=task_id,
            role="reviewer",
            model=secondary_model,
            label="secondary-review",
            prompt=build_agent_prompt(
                task,
                role="reviewer",
                patch=patch_path.read_text(encoding="utf-8", errors="replace"),
            ),
            worktree=worktree,
            run_dir=run_dir,
            timeout_seconds=settings.roles["reviewer"].timeout_seconds,
            settings=settings,
            paths=paths,
        )
        policy_rejections = [
            rejection
            for rejection in find_agent_policy_rejections(run_dir)
            if rejection.startswith("secondary-review:")
        ]
        if policy_rejections:
            record_model_safety_violation(
                secondary_model,
                settings.models[secondary_model].digest,
                privacy=False,
                reason="The secondary local reviewer attempted a forbidden command.",
                settings=settings,
                paths=paths,
            )
            raise AgentProcessError(
                "Secondary reviewer attempted a forbidden command.",
                status="blocked",
            )
        secondary_payload = {
            **review.model_dump(mode="json"),
            "model": secondary_model,
            "model_digest": settings.models[secondary_model].digest,
        }
    except AgentProcessError as exc:
        secondary_payload = {
            "status": "blocked",
            "summary": "Secondary local review did not complete.",
            "blocking_reason": str(exc),
            "findings": [],
            "model": secondary_model,
            "model_digest": settings.models[secondary_model].digest,
        }
    _update_run(
        task_id,
        db_path=paths.db_path,
        secondary_review_json=_json_dump(secondary_payload),
    )
    refreshed = get_run(task_id, db_path=paths.db_path)
    if refreshed is None:
        raise CoordinatorError("Run disappeared after secondary review.")
    final_eligibility = auto_apply_eligibility(
        refreshed, settings=settings, paths=paths, require_secondary_review=True
    )
    if not final_eligibility["eligible"]:
        set_autonomy_paused(
            True,
            reason="Independent reviewers did not agree on an auto-apply candidate.",
            settings=settings,
            paths=paths,
        )
        return refreshed
    approve_run(
        task_id,
        reviewed_by=AUTO_APPLY_POLICY_VERSION,
        settings=settings,
        paths=paths,
    )
    return apply_run(
        task_id,
        release_check=False,
        settings=settings,
        paths=paths,
    )


def apply_run(
    task_id: str,
    *,
    release_check: bool,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run was not found.")
    if run["status"] != "approved":
        raise CoordinatorError("Patch requires Main Codex approval before application.")
    patch_path = Path(str(run.get("patch_path") or ""))
    if not patch_path.is_file():
        raise CoordinatorError("Approved patch is missing.")
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    if digest != run.get("patch_sha256") or digest != run.get("reviewed_patch_sha256"):
        raise CoordinatorError("Patch no longer matches its review receipt.")
    try:
        _assert_patch_fresh(run, paths=paths)
        check = _git(
            ["apply", "--check", "--whitespace=nowarn", str(patch_path)],
            cwd=paths.repo_root,
            check=False,
        )
        if check.returncode != 0:
            raise CoordinatorError(
                check.stderr.strip() or "Patch no longer applies cleanly."
            )
    except CoordinatorError as exc:
        _update_run(
            task_id,
            db_path=paths.db_path,
            status="stale",
            phase="stale",
            finished_at=utc_now_iso(),
            error=str(exc),
        )
        raise

    backup = create_workspace_backup(task_id=task_id, paths=paths)
    applied = _git(
        ["apply", "--whitespace=nowarn", str(patch_path)],
        cwd=paths.repo_root,
        check=False,
    )
    if applied.returncode != 0:
        raise CoordinatorError(
            applied.stderr.strip()
            or f"Patch failed after backup was saved at {backup}."
        )
    task = AgentTaskSpec.model_validate(run["task"])
    run_dir = paths.runtime_root / "runs" / task_id / "post-apply"
    run_dir.mkdir(parents=True, exist_ok=True)
    post_checks = run_checks(
        task.acceptance_checks,
        worktree=paths.repo_root,
        run_dir=run_dir,
        task_id=task_id,
        settings=settings,
        paths=paths,
    )
    release_result: dict[str, Any] | None = None
    if release_check:
        started = time.monotonic()
        process = subprocess.run(
            [str(paths.repo_root / "scripts" / "verify_release.sh")],  # noqa: S603
            cwd=paths.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        release_result = {
            "name": "verify-release",
            "status": "passed" if process.returncode == 0 else "failed",
            "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": _redact_stream(process.stdout),
            "stderr": _redact_stream(process.stderr),
        }
    checks_ok = all(item.status == "passed" for item in post_checks)
    release_ok = release_result is None or release_result["status"] == "passed"
    verification_payload: list[dict[str, Any]] = [
        item.model_dump(mode="json") for item in post_checks
    ]
    if release_result:
        verification_payload.append(release_result)
    policy_auto_apply = run.get("reviewed_by") == AUTO_APPLY_POLICY_VERSION
    if policy_auto_apply and not (checks_ok and release_ok):
        reverse_check = _git(
            [
                "apply",
                "-R",
                "--check",
                "--whitespace=nowarn",
                str(patch_path),
            ],
            cwd=paths.repo_root,
            check=False,
        )
        rolled_back = False
        rollback_error = reverse_check.stderr.strip()
        if reverse_check.returncode == 0:
            reverse = _git(
                ["apply", "-R", "--whitespace=nowarn", str(patch_path)],
                cwd=paths.repo_root,
                check=False,
            )
            rolled_back = reverse.returncode == 0
            rollback_error = reverse.stderr.strip()
        _update_run(
            task_id,
            db_path=paths.db_path,
            status="blocked",
            phase=(
                "auto_apply_rolled_back"
                if rolled_back
                else "auto_apply_rollback_failed"
            ),
            finished_at=utc_now_iso(),
            post_apply_verification_json=_json_dump(verification_payload),
            error=(
                "Auto-applied patch failed verification and was rolled back."
                if rolled_back
                else "Auto-applied patch failed verification and could not be rolled back safely. "
                + (rollback_error or "Use the recorded workspace backup.")
            ),
            safety_json=_json_dump(
                {
                    **run.get("safety", {}),
                    "backup_path": str(backup),
                    "post_apply_ok": False,
                    "auto_apply_rollback_succeeded": rolled_back,
                }
            ),
        )
        _record_apply_result(
            task_id,
            safe=False,
            first_pass=False,
            settings=settings,
            paths=paths,
        )
        set_autonomy_paused(
            True,
            reason="An auto-applied patch failed post-apply verification.",
            settings=settings,
            paths=paths,
        )
        result = get_run(task_id, db_path=paths.db_path)
        if result is None:
            raise CoordinatorError("Failed auto-apply run disappeared.")
        return result
    _update_run(
        task_id,
        db_path=paths.db_path,
        status="applied",
        phase="applied",
        finished_at=utc_now_iso(),
        post_apply_verification_json=_json_dump(verification_payload),
        error=""
        if checks_ok and release_ok
        else "Applied patch has failing verification.",
        safety_json=_json_dump(
            {
                **run.get("safety", {}),
                "backup_path": str(backup),
                "post_apply_ok": checks_ok and release_ok,
                "release_check_requested": release_check,
            }
        ),
    )
    if task.acceptance_checks:
        _record_apply_result(
            task_id,
            safe=checks_ok and release_ok,
            first_pass=int(run.get("attempt") or 0) == 1,
            settings=settings,
            paths=paths,
        )
    worktree_value = run.get("worktree_path")
    if worktree_value:
        cleanup_worktree(Path(str(worktree_value)), paths=paths, force=True)
    result = get_run(task_id, db_path=paths.db_path)
    if result is None:
        raise CoordinatorError("Applied run disappeared.")
    return result


def verify_run(
    task_id: str,
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run was not found.")
    worktree_value = run.get("worktree_path")
    if not worktree_value or not Path(str(worktree_value)).is_dir():
        raise CoordinatorError("Run worktree is unavailable.")
    task = AgentTaskSpec.model_validate(run["task"])
    run_dir = paths.runtime_root / "runs" / task_id / "manual-verification"
    run_dir.mkdir(parents=True, exist_ok=True)
    checks = run_checks(
        task.acceptance_checks,
        worktree=Path(str(worktree_value)),
        run_dir=run_dir,
        task_id=task_id,
        settings=settings,
        paths=paths,
    )
    _update_run(
        task_id,
        db_path=paths.db_path,
        verification_json=_json_dump([item.model_dump(mode="json") for item in checks]),
    )
    result = get_run(task_id, db_path=paths.db_path)
    if result is None:
        raise CoordinatorError("Verified run disappeared.")
    return result


def cancel_run(task_id: str, *, paths: CoordinatorPaths) -> dict[str, Any]:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run was not found.")
    if run["status"] not in ACTIVE_STATUSES:
        raise CoordinatorError(f"Run cannot be cancelled from status {run['status']}.")
    with connect(paths.db_path) as con:
        row = con.execute(
            "SELECT child_pid FROM local_agent_runs WHERE task_id = ?", (task_id,)
        ).fetchone()
        con.execute(
            """
            UPDATE local_agent_runs
            SET cancel_requested = 1, phase = 'cancel_requested'
            WHERE task_id = ?
            """,
            (task_id,),
        )
    pid = int(row["child_pid"]) if row and row["child_pid"] else None
    if pid:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    result = get_run(task_id, db_path=paths.db_path)
    if result is None:
        raise CoordinatorError("Cancelled run disappeared.")
    return result


def reject_run(task_id: str, *, paths: CoordinatorPaths) -> dict[str, Any]:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run was not found.")
    if run["status"] in ACTIVE_STATUSES or run["status"] == "applied":
        raise CoordinatorError(f"Run cannot be rejected from status {run['status']}.")
    worktree_value = run.get("worktree_path")
    if worktree_value:
        cleanup_worktree(Path(str(worktree_value)), paths=paths, force=True)
    return _finish_run(
        task_id,
        status="rejected",
        phase="rejected",
        paths=paths,
    )


def export_patch(task_id: str, destination: Path, *, paths: CoordinatorPaths) -> Path:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None or not run.get("patch_path"):
        raise CoordinatorError("Run has no patch to export.")
    source = Path(str(run["patch_path"]))
    if not source.is_file():
        raise CoordinatorError("Run patch is missing.")
    target = destination.expanduser().resolve()
    if target.is_dir():
        target = target / f"{task_id}.patch"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target
