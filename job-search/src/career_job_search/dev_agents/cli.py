"""Command-line adapter for the local development-agent coordinator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from career_job_search.core.contracts import helper_json
from career_job_search.dev_agents.application import (
    apply_run,
    cancel_run,
    export_patch,
    reject_run,
    verify_run,
)
from career_job_search.dev_agents.benchmark import benchmark
from career_job_search.dev_agents.common import (
    DEFAULT_BACKUP_ROOT,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_WORKTREE_ROOT,
    JOB_ROOT,
    CoordinatorError,
    CoordinatorPaths,
    load_settings,
)
from career_job_search.dev_agents.doctor import doctor
from career_job_search.dev_agents.planner import run_planner
from career_job_search.dev_agents.proposals import (
    approve_proposal,
    get_proposal,
    list_proposals,
    reject_proposal,
)
from career_job_search.dev_agents.review import (
    _load_task_input,
    approve_run,
    evaluate_autonomy,
    set_autonomy_paused,
)
from career_job_search.dev_agents.run_flow import execute_run
from career_job_search.dev_agents.runs import (
    create_run,
    get_rollout,
    get_run,
    init_db,
)
from career_job_search.dev_agents.service import (
    _coordinator_command,
    _spawn_service_child,
    build_overview,
    cleanup_old_runs,
    run_development_agent_service,
    run_worker,
    spawn_worker,
)


def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, indent=2))


def _paths_from_args(args: argparse.Namespace) -> CoordinatorPaths:
    return CoordinatorPaths(
        repo_root=args.repo_root.expanduser().resolve(),
        runtime_root=args.runtime_root.expanduser().resolve(),
        db_path=args.db.expanduser().resolve(),
        worktree_root=args.worktree_root.expanduser().resolve(),
        backup_root=args.backup_root.expanduser().resolve(),
        config_path=args.config.expanduser().resolve(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe local Ollama development-agent coordinator"
    )
    parser.add_argument("--repo-root", type=Path, default=JOB_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--worktree-root", type=Path, default=DEFAULT_WORKTREE_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor")
    benchmark_parser = sub.add_parser("benchmark")
    benchmark_parser.add_argument("--candidate")
    model_benchmark = sub.add_parser("model-benchmark")
    model_benchmark.add_argument("--candidate", required=True)
    model_benchmark.add_argument("--background", action="store_true")
    sub.add_parser("rollout")
    sub.add_parser("autonomy")

    autonomy_pause = sub.add_parser("autonomy-pause")
    autonomy_pause.add_argument(
        "--reason", default="Paused manually from the local dashboard."
    )
    sub.add_parser("autonomy-resume")

    status = sub.add_parser("status")
    status.add_argument("--limit", type=int, default=30)

    show = sub.add_parser("show")
    show.add_argument("--task-id", required=True)

    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument(
        "--trigger-source",
        choices=("manual", "scheduled", "schedule_catch_up"),
        default="manual",
    )
    plan_parser.add_argument("--scheduled-for")
    plan_parser.add_argument("--background", action="store_true")

    proposals = sub.add_parser("proposals")
    proposals.add_argument("--status")
    proposals.add_argument("--limit", type=int, default=50)

    proposal_show = sub.add_parser("proposal-show")
    proposal_show.add_argument("--proposal-id", required=True)

    proposal_approve = sub.add_parser("proposal-approve")
    proposal_approve.add_argument("--proposal-id", required=True)
    proposal_approve.add_argument("--objective")
    proposal_approve.add_argument("--allowed-path", action="append")
    proposal_approve.add_argument(
        "--check-preset", choices=("none", "python", "dashboard", "architecture")
    )
    proposal_approve.add_argument("--spawn-worker", action="store_true")

    proposal_reject = sub.add_parser("proposal-reject")
    proposal_reject.add_argument("--proposal-id", required=True)

    for command in ("run", "enqueue"):
        task_parser = sub.add_parser(command)
        source = task_parser.add_mutually_exclusive_group()
        source.add_argument("--task-file", type=Path)
        source.add_argument("--task-json")
        if command == "enqueue":
            task_parser.add_argument("--spawn-worker", action="store_true")

    worker = sub.add_parser("worker")
    worker.add_argument("--once", action="store_true")

    service = sub.add_parser("service")
    service.add_argument("--poll-seconds", type=float, default=5)

    verify = sub.add_parser("verify")
    verify.add_argument("--task-id", required=True)

    approve = sub.add_parser("approve")
    approve.add_argument("--task-id", required=True)
    approve.add_argument("--reviewed-by", default="main-codex")

    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--task-id", required=True)
    apply_parser.add_argument("--release-check", action="store_true")

    cancel = sub.add_parser("cancel")
    cancel.add_argument("--task-id", required=True)

    reject = sub.add_parser("reject")
    reject.add_argument("--task-id", required=True)

    export = sub.add_parser("export-patch")
    export.add_argument("--task-id", required=True)
    export.add_argument("--destination", type=Path, required=True)

    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--older-than-days", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = _paths_from_args(args)
    try:
        settings = load_settings(paths.config_path)
        init_db(paths.db_path, settings=settings)
        exit_code = 0
        if args.cmd == "doctor":
            data = doctor(settings=settings, paths=paths)
            exit_code = 0 if data["ok"] else 1
        elif args.cmd in {"benchmark", "model-benchmark"}:
            candidate = args.candidate or settings.implementer_candidates[0]
            if getattr(args, "background", False):
                process = _spawn_service_child(
                    _coordinator_command(
                        paths, "model-benchmark", "--candidate", candidate
                    ),
                    label="model-benchmark",
                    paths=paths,
                )
                data = {"started": True, "pid": process.pid, "candidate": candidate}
            else:
                data = benchmark(
                    settings=settings, paths=paths, candidate_model=candidate
                )
                exit_code = 0 if data["qualified"] else 1
        elif args.cmd == "rollout":
            data = get_rollout(settings=settings, db_path=paths.db_path)
        elif args.cmd == "autonomy":
            data = evaluate_autonomy(settings=settings, paths=paths)
        elif args.cmd == "autonomy-pause":
            data = set_autonomy_paused(
                True,
                reason=args.reason,
                settings=settings,
                paths=paths,
            )
        elif args.cmd == "autonomy-resume":
            data = set_autonomy_paused(
                False,
                reason="",
                settings=settings,
                paths=paths,
            )
        elif args.cmd == "status":
            data = build_overview(settings=settings, paths=paths, limit=args.limit)
        elif args.cmd == "show":
            data = get_run(args.task_id, db_path=paths.db_path)
            if data is None:
                raise CoordinatorError("Local-agent run was not found.")
        elif args.cmd == "plan":
            if args.background:
                command = [
                    "plan",
                    "--trigger-source",
                    args.trigger_source,
                ]
                if args.scheduled_for:
                    command.extend(["--scheduled-for", args.scheduled_for])
                process = _spawn_service_child(
                    _coordinator_command(paths, *command),
                    label="planner-manual",
                    paths=paths,
                )
                data = {"started": True, "pid": process.pid}
            else:
                data = run_planner(
                    trigger_source=args.trigger_source,
                    scheduled_for=args.scheduled_for,
                    settings=settings,
                    paths=paths,
                )
                exit_code = 0 if data["status"] == "completed" else 1
        elif args.cmd == "proposals":
            data = {
                "proposals": list_proposals(
                    db_path=paths.db_path, status=args.status, limit=args.limit
                )
            }
        elif args.cmd == "proposal-show":
            data = get_proposal(args.proposal_id, db_path=paths.db_path)
            if data is None:
                raise CoordinatorError("Local-agent proposal was not found.")
        elif args.cmd == "proposal-approve":
            data = approve_proposal(
                args.proposal_id,
                settings=settings,
                paths=paths,
                objective=args.objective,
                allowed_paths=args.allowed_path,
                check_preset=args.check_preset,
            )
            if args.spawn_worker:
                data["worker_pid"] = spawn_worker(paths=paths)
        elif args.cmd == "proposal-reject":
            data = reject_proposal(args.proposal_id, paths=paths)
        elif args.cmd in {"run", "enqueue"}:
            task = _load_task_input(args.task_file, args.task_json)
            created = create_run(task, settings=settings, paths=paths)
            if args.cmd == "run":
                data = execute_run(created["task_id"], settings=settings, paths=paths)
                exit_code = (
                    0 if data["status"] in {"ready_for_codex_review", "applied"} else 1
                )
            else:
                worker_pid = spawn_worker(paths=paths) if args.spawn_worker else None
                data = {"run": created, "worker_pid": worker_pid}
        elif args.cmd == "worker":
            data = {
                "completed": run_worker(once=args.once, settings=settings, paths=paths)
            }
        elif args.cmd == "service":
            return run_development_agent_service(
                poll_seconds=args.poll_seconds,
                settings=settings,
                paths=paths,
            )
        elif args.cmd == "verify":
            data = verify_run(args.task_id, settings=settings, paths=paths)
            exit_code = (
                0
                if all(item.get("status") == "passed" for item in data["verification"])
                else 1
            )
        elif args.cmd == "approve":
            data = approve_run(
                args.task_id,
                reviewed_by=args.reviewed_by,
                settings=settings,
                paths=paths,
            )
        elif args.cmd == "apply":
            data = apply_run(
                args.task_id,
                release_check=args.release_check,
                settings=settings,
                paths=paths,
            )
            exit_code = 0 if not data["error"] else 1
        elif args.cmd == "cancel":
            data = cancel_run(args.task_id, paths=paths)
        elif args.cmd == "reject":
            data = reject_run(args.task_id, paths=paths)
        elif args.cmd == "export-patch":
            data = {
                "path": str(export_patch(args.task_id, args.destination, paths=paths))
            }
        elif args.cmd == "cleanup":
            days = args.older_than_days or settings.limits.retention_days
            if days < 1:
                raise CoordinatorError("Cleanup retention must be at least one day.")
            data = cleanup_old_runs(older_than_days=days, paths=paths)
        else:
            raise CoordinatorError(f"Unsupported command: {args.cmd}")
    except (CoordinatorError, OSError, ValidationError, ValueError) as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": data})
    return exit_code
