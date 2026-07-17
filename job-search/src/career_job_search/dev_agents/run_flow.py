"""End-to-end execution flow for one local development-agent task."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from career_job_search.dev_agents.application import maybe_auto_apply_run
from career_job_search.dev_agents.common import (
    AgentProcessError,
    CoordinatorError,
    CoordinatorPaths,
    _json_dump,
    utc_now_iso,
)
from career_job_search.dev_agents.execution import (
    _finish_run,
    _patch_result,
    _run_with_process_retry,
    _selected_implementer_identity,
    build_agent_prompt,
    find_agent_policy_rejections,
    run_agent_process,
    run_checks,
)
from career_job_search.dev_agents.models import (
    AgentFinding,
    AgentRole,
    AgentTaskSpec,
    LocalAgentSettings,
)
from career_job_search.dev_agents.planner import resource_status
from career_job_search.dev_agents.policy import validate_task_policy
from career_job_search.dev_agents.review import record_model_safety_violation
from career_job_search.dev_agents.runs import _update_run, get_run, validate_task_id
from career_job_search.dev_agents.snapshots import build_patch, create_snapshot


def execute_run(
    task_id: str,
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    """Execute a queued task synchronously."""

    clean_id = validate_task_id(task_id)
    run = get_run(clean_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run was not found.")
    if run["status"] not in {"queued", "snapshotting"}:
        raise CoordinatorError(f"Run cannot start from status {run['status']}.")
    task = AgentTaskSpec.model_validate(run["task"])
    validate_task_policy(task, settings=settings)
    run_dir = paths.runtime_root / "runs" / clean_id
    model = str(run.get("model") or settings.roles[task.role].model)
    model_digest = str(run.get("model_digest") or settings.models[model].digest)

    resource_role: AgentRole = (
        "implementer" if task.role == "implementer" else "planner"
    )
    resources = resource_status(resource_role, settings=settings, paths=paths)
    if not resources["ok"]:
        _update_run(
            clean_id,
            db_path=paths.db_path,
            status="queued",
            phase="resource_deferred",
            started_at=None,
            error=f"Deferred: {resources['reason']}",
            safety_json=_json_dump({"resource_status": resources}),
        )
        deferred = get_run(clean_id, db_path=paths.db_path)
        if deferred is None:
            raise CoordinatorError("Deferred run disappeared.")
        return deferred

    if task.role == "implementer":
        try:
            model, model_digest = _selected_implementer_identity(
                settings=settings, paths=paths
            )
        except CoordinatorError as exc:
            return _finish_run(
                clean_id,
                status="blocked",
                phase="qualification_required",
                paths=paths,
                error=str(exc),
            )
    else:
        model = settings.roles[task.role].model
        model_digest = settings.models[model].digest

    _update_run(
        clean_id,
        db_path=paths.db_path,
        status="snapshotting",
        phase="snapshotting",
        model=model,
        model_digest=model_digest,
        started_at=utc_now_iso(),
        error="",
    )
    try:
        snapshot = create_snapshot(clean_id, settings=settings, paths=paths)
        _update_run(
            clean_id,
            db_path=paths.db_path,
            snapshot_commit=snapshot.commit,
            worktree_path=str(snapshot.worktree),
            status="running",
            phase=task.role,
            safety_json=_json_dump(
                {
                    "offline_only": True,
                    "active_workspace_writable": False,
                    "excluded_snapshot_paths": list(snapshot.excluded_paths),
                    "git_history_mutations_allowed": False,
                }
            ),
        )

        attempts_remaining = settings.limits.retry_count
        response, attempts_remaining = _run_with_process_retry(
            task_id=clean_id,
            role=task.role,
            model=model,
            label_prefix=task.role,
            prompt=build_agent_prompt(task, role=task.role),
            worktree=snapshot.worktree,
            run_dir=run_dir,
            timeout_seconds=int(
                task.timeout_seconds or settings.roles[task.role].timeout_seconds
            ),
            settings=settings,
            paths=paths,
            attempts_remaining=attempts_remaining,
        )
        policy_rejections = find_agent_policy_rejections(run_dir)
        if policy_rejections:
            record_model_safety_violation(
                model,
                model_digest,
                privacy=False,
                reason=f"A local {task.role} attempted a forbidden command.",
                settings=settings,
                paths=paths,
            )
            return _finish_run(
                clean_id,
                status="blocked",
                phase="agent_policy_violation",
                paths=paths,
                error="The local model attempted a forbidden command.",
                result_json=response.model_dump_json(),
                safety_json=_json_dump(
                    {
                        "offline_only": True,
                        "active_workspace_writable": False,
                        "excluded_snapshot_paths": list(snapshot.excluded_paths),
                        "git_history_mutations_allowed": False,
                        "policy_rejections": policy_rejections,
                    }
                ),
            )
        if response.status == "blocked":
            return _finish_run(
                clean_id,
                status="blocked",
                phase="model_blocked",
                paths=paths,
                error=response.blocking_reason or "Local model reported a blocker.",
                result_json=response.model_dump_json(),
            )

        if task.role != "implementer":
            _update_run(
                clean_id,
                db_path=paths.db_path,
                status="verifying",
                phase="verifying",
                result_json=response.model_dump_json(),
            )
            checks = run_checks(
                task.acceptance_checks,
                worktree=snapshot.worktree,
                run_dir=run_dir,
                task_id=clean_id,
                settings=settings,
                paths=paths,
            )
            failed = next((item for item in checks if item.status != "passed"), None)
            if failed:
                return _finish_run(
                    clean_id,
                    status="blocked",
                    phase="verification_failed",
                    paths=paths,
                    error=f"Verification failed: {failed.name}",
                    verification_json=_json_dump(
                        [item.model_dump(mode="json") for item in checks]
                    ),
                )
            return _finish_run(
                clean_id,
                status="ready_for_codex_review",
                phase="ready_for_codex_review",
                paths=paths,
                verification_json=_json_dump(
                    [item.model_dump(mode="json") for item in checks]
                ),
            )

        patch = build_patch(task, snapshot, settings=settings, run_dir=run_dir)
        result = _patch_result(response, patch)
        _update_run(
            clean_id,
            db_path=paths.db_path,
            patch_path=str(patch.path),
            patch_sha256=patch.sha256,
            result_json=_json_dump(result),
            status="local_review",
            phase="local_review",
        )

        review_prompt = build_agent_prompt(
            task,
            role="reviewer",
            patch=patch.path.read_text(encoding="utf-8", errors="replace"),
        )
        review, attempts_remaining = _run_with_process_retry(
            task_id=clean_id,
            role="reviewer",
            model=settings.roles["reviewer"].model,
            label_prefix="review",
            prompt=review_prompt,
            worktree=snapshot.worktree,
            run_dir=run_dir,
            timeout_seconds=settings.roles["reviewer"].timeout_seconds,
            settings=settings,
            paths=paths,
            attempts_remaining=attempts_remaining,
        )
        blocking_findings = [
            item for item in review.findings if item.severity in {"critical", "major"}
        ]
        if (review.status == "blocked" or blocking_findings) and attempts_remaining > 0:
            attempts_remaining -= 1
            feedback = blocking_findings or [
                AgentFinding(
                    severity="major",
                    title="Reviewer could not complete approval",
                    detail=review.blocking_reason or "Resolve the review blocker.",
                )
            ]
            _update_run(
                clean_id,
                db_path=paths.db_path,
                status="running",
                phase="implementer_retry",
                attempt=2,
            )
            response = run_agent_process(
                task_id=clean_id,
                role="implementer",
                model=model,
                label="implementer-2",
                prompt=build_agent_prompt(
                    task,
                    role="implementer",
                    reviewer_feedback=feedback,
                ),
                worktree=snapshot.worktree,
                run_dir=run_dir,
                timeout_seconds=int(task.timeout_seconds or 1500),
                settings=settings,
                paths=paths,
            )
            if response.status == "blocked":
                return _finish_run(
                    clean_id,
                    status="blocked",
                    phase="model_blocked",
                    paths=paths,
                    error=response.blocking_reason or "Implementer retry was blocked.",
                )
            patch = build_patch(task, snapshot, settings=settings, run_dir=run_dir)
            result = _patch_result(response, patch)
            review = run_agent_process(
                task_id=clean_id,
                role="reviewer",
                model=settings.roles["reviewer"].model,
                label="review-2",
                prompt=build_agent_prompt(
                    task,
                    role="reviewer",
                    patch=patch.path.read_text(encoding="utf-8", errors="replace"),
                ),
                worktree=snapshot.worktree,
                run_dir=run_dir,
                timeout_seconds=settings.roles["reviewer"].timeout_seconds,
                settings=settings,
                paths=paths,
            )
            blocking_findings = [
                item
                for item in review.findings
                if item.severity in {"critical", "major"}
            ]

        policy_rejections = find_agent_policy_rejections(run_dir)
        if policy_rejections:
            implicated: set[tuple[str, str]] = set()
            for rejection in policy_rejections:
                if rejection.startswith("review-"):
                    reviewer_model = settings.roles["reviewer"].model
                    implicated.add(
                        (reviewer_model, settings.models[reviewer_model].digest)
                    )
                else:
                    implicated.add((model, model_digest))
            for rejected_model, rejected_digest in implicated:
                record_model_safety_violation(
                    rejected_model,
                    rejected_digest,
                    privacy=False,
                    reason="A local implementation or review agent attempted a forbidden command.",
                    settings=settings,
                    paths=paths,
                )
            return _finish_run(
                clean_id,
                status="blocked",
                phase="agent_policy_violation",
                paths=paths,
                error="A local implementation or review agent attempted a forbidden command.",
                safety_json=_json_dump(
                    {
                        "offline_only": True,
                        "active_workspace_writable": False,
                        "excluded_snapshot_paths": list(snapshot.excluded_paths),
                        "git_history_mutations_allowed": False,
                        "policy_rejections": policy_rejections,
                    }
                ),
            )

        _update_run(
            clean_id,
            db_path=paths.db_path,
            patch_path=str(patch.path),
            patch_sha256=patch.sha256,
            reviewed_patch_sha256=None,
            reviewed_by=None,
            reviewed_at=None,
            result_json=_json_dump(result),
            local_review_json=_json_dump(
                {
                    **review.model_dump(mode="json"),
                    "model": settings.roles["reviewer"].model,
                    "model_digest": settings.models[
                        settings.roles["reviewer"].model
                    ].digest,
                }
            ),
        )
        if review.status == "blocked" or blocking_findings:
            summary = "; ".join(item.title for item in blocking_findings)
            return _finish_run(
                clean_id,
                status="blocked",
                phase="local_review_blocked",
                paths=paths,
                error=review.blocking_reason or summary or "Local review did not pass.",
            )

        _update_run(
            clean_id,
            db_path=paths.db_path,
            status="verifying",
            phase="verifying",
        )
        checks = run_checks(
            task.acceptance_checks,
            worktree=snapshot.worktree,
            run_dir=run_dir,
            task_id=clean_id,
            settings=settings,
            paths=paths,
        )
        failed = next((item for item in checks if item.status != "passed"), None)
        if failed:
            return _finish_run(
                clean_id,
                status="blocked",
                phase="verification_failed",
                paths=paths,
                error=f"Verification failed: {failed.name}",
                verification_json=_json_dump(
                    [item.model_dump(mode="json") for item in checks]
                ),
            )
        ready = _finish_run(
            clean_id,
            status="ready_for_codex_review",
            phase="ready_for_codex_review",
            paths=paths,
            verification_json=_json_dump(
                [item.model_dump(mode="json") for item in checks]
            ),
        )
        if ready["role"] == "implementer":
            return maybe_auto_apply_run(clean_id, settings=settings, paths=paths)
        return ready
    except AgentProcessError as exc:
        policy_rejections = find_agent_policy_rejections(run_dir)
        if policy_rejections:
            record_model_safety_violation(
                model,
                model_digest,
                privacy=False,
                reason=f"A local {task.role} attempted a forbidden command.",
                settings=settings,
                paths=paths,
            )
            return _finish_run(
                clean_id,
                status="blocked",
                phase="agent_policy_violation",
                paths=paths,
                error="The local model attempted a forbidden command.",
                safety_json=_json_dump(
                    {
                        "offline_only": True,
                        "active_workspace_writable": False,
                        "policy_rejections": policy_rejections,
                    }
                ),
            )
        return _finish_run(
            clean_id,
            status=exc.status,
            phase=exc.status,
            paths=paths,
            error=str(exc),
        )
    except (CoordinatorError, OSError, ValidationError) as exc:
        message = str(exc)
        if task.role == "implementer" and any(
            marker in message.casefold()
            for marker in (
                "outside allowed paths",
                "protected path",
                "sensitive artifact",
                "external symlink",
                "forbidden snapshot",
            )
        ):
            record_model_safety_violation(
                model,
                model_digest,
                privacy="sensitive" in message.casefold()
                or "external symlink" in message.casefold(),
                reason=f"Local-agent safety policy stopped a patch: {message[:500]}",
                settings=settings,
                paths=paths,
            )
        return _finish_run(
            clean_id,
            status="failed",
            phase="failed",
            paths=paths,
            error=str(exc),
        )
