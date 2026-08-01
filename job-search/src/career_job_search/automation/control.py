#!/usr/bin/env python3
"""Local task queue and worker for the Career dashboard.

The dashboard may enqueue only the fixed actions returned by
``command_for_kind``. It can never provide a command, executable, path, or
shell fragment. This keeps the web layer small while long-running Python work
happens in a separate process.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from career_job_search.automation.overview import (
    _latest_worker,
    _source_health,
    build_overview,
)
from career_job_search.automation.queue import (
    ACTIVE_STATUSES,
    CATCH_UP_AFTER_MINUTES,
    DEFAULT_AUTOMATION_DB,
    DEFAULT_LOG_DIR,
    DEFAULT_OPPORTUNITY_CONFIG,
    JOB_ROOT,
    MAX_CAPTURE_BYTES,
    RUN_KIND_CV_BUILD,
    RUN_KIND_DAILY_SEARCH,
    RUN_KINDS,
    SCHEDULE_TIME_PATTERN,
    SCHEMA_SQL,
    SOURCE_STALE_HOURS,
    STALE_RUN_MINUTES,
    TERMINAL_STATUSES,
    WORKER_ONLINE_SECONDS,
    _claim_next_run,
    _json_dump,
    _json_load,
    _recover_stale_runs,
    _row_to_run,
    cancel_run,
    connect,
    enqueue_due_schedule,
    enqueue_run,
    get_run,
    get_settings,
    init_db,
    list_runs,
    retry_run,
    update_schedule,
    utc_now,
    utc_now_iso,
    validate_kind,
    validate_run_id,
    validate_schedule_time,
    validate_timezone,
)
from career_job_search.core.contracts import helper_json

__all__ = [
    "ACTIVE_STATUSES",
    "CATCH_UP_AFTER_MINUTES",
    "DEFAULT_AUTOMATION_DB",
    "DEFAULT_LOG_DIR",
    "DEFAULT_OPPORTUNITY_CONFIG",
    "JOB_ROOT",
    "MAX_CAPTURE_BYTES",
    "RUN_KIND_CV_BUILD",
    "RUN_KIND_DAILY_SEARCH",
    "RUN_KINDS",
    "SCHEMA_SQL",
    "SCHEDULE_TIME_PATTERN",
    "SOURCE_STALE_HOURS",
    "STALE_RUN_MINUTES",
    "TERMINAL_STATUSES",
    "WORKER_ONLINE_SECONDS",
    "_claim_next_run",
    "_json_dump",
    "_json_load",
    "_latest_worker",
    "_recover_stale_runs",
    "_row_to_run",
    "_source_health",
    "build_overview",
    "cancel_run",
    "connect",
    "enqueue_due_schedule",
    "enqueue_run",
    "get_run",
    "get_settings",
    "init_db",
    "list_runs",
    "retry_run",
    "update_schedule",
    "utc_now",
    "utc_now_iso",
    "validate_kind",
    "validate_run_id",
    "validate_schedule_time",
    "validate_timezone",
]

def command_for_kind(kind: str) -> tuple[list[str], int]:
    clean_kind = validate_kind(kind)
    if clean_kind == RUN_KIND_DAILY_SEARCH:
        return (
            [
                sys.executable,
                str(JOB_ROOT / "tools" / "opportunity_orchestrate.py"),
                "--config",
                str(DEFAULT_OPPORTUNITY_CONFIG),
                "daily-queue",
                "--exclude-linkedin",
            ],
            20 * 60,
        )
    return (
        [
            sys.executable,
            str(JOB_ROOT / "cv" / "build_cv_pdf.py"),
            "--all",
        ],
        10 * 60,
    )


def _update_run(
    run_id: str,
    *,
    db_path: Path | str,
    fields: dict[str, Any],
) -> None:
    allowed = {
        "status",
        "phase",
        "progress",
        "heartbeat_at",
        "child_pid",
        "finished_at",
        "result_json",
        "stdout",
        "stderr",
        "error",
    }
    if not fields or not set(fields).issubset(allowed):
        raise ValueError("Unsupported automation run update.")
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = [fields[name] for name in fields]
    with connect(db_path) as con:
        con.execute(
            f"UPDATE automation_runs SET {assignments} WHERE run_id = ?",  # noqa: S608 - field names are fixed above
            (*values, run_id),
        )


def _read_tail(path: Path, max_bytes: int = MAX_CAPTURE_BYTES) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read(max_bytes)
    return data.decode("utf-8", errors="replace")


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait(timeout=5)


def _cv_output_summary() -> dict[str, Any]:
    output_dir = JOB_ROOT / "output"
    pdfs = []
    for path in sorted(output_dir.glob("andrej-spirov-cv-*.pdf")):
        try:
            stat = path.stat()
        except OSError:
            continue
        pdfs.append(
            {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, UTC)
                .replace(microsecond=0)
                .isoformat(),
            }
        )
    return {"pdf_count": len(pdfs), "pdfs": pdfs}


def _result_from_process(
    *, kind: str, returncode: int, stdout: str, stderr: str
) -> tuple[str, dict[str, Any], str]:
    if kind == RUN_KIND_CV_BUILD:
        if returncode == 0:
            return "succeeded", _cv_output_summary(), ""
        return "failed", {}, stderr.strip() or stdout.strip() or "CV build failed."

    payload = _json_load(stdout, None)
    if not isinstance(payload, dict):
        return "failed", {}, stderr.strip() or "Daily search returned invalid JSON."
    if not payload.get("ok"):
        return (
            "failed",
            {},
            str(payload.get("error") or stderr or "Daily search failed."),
        )
    result = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if returncode == 2 or result.get("partial"):
        return (
            "partial",
            result,
            "Some job sources were unavailable; available results were kept.",
        )
    if returncode != 0:
        return "failed", result, stderr.strip() or "Daily search failed."
    return "succeeded", result, ""


def _run_status(run_id: str, *, db_path: Path | str = DEFAULT_AUTOMATION_DB) -> str:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT status FROM automation_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    return str(row["status"]) if row else "missing"


def execute_run(
    run: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    log_dir: Path | str = DEFAULT_LOG_DIR,
) -> dict[str, Any]:
    run_id = validate_run_id(str(run["run_id"]))
    kind = validate_kind(str(run["kind"]))
    command, timeout_seconds = command_for_kind(kind)
    logs = Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / f"{run_id}.stdout.log"
    stderr_path = logs / f"{run_id}.stderr.log"
    stdout_path.touch(mode=0o600, exist_ok=True)
    stderr_path.touch(mode=0o600, exist_ok=True)
    stdout_path.chmod(0o600)
    stderr_path.chmod(0o600)

    process: subprocess.Popen[Any] | None = None
    started = time.monotonic()
    cancelled = False
    timed_out = False
    try:
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_handle,
            stderr_path.open("w", encoding="utf-8") as stderr_handle,
        ):
            process = subprocess.Popen(
                command,
                cwd=JOB_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                shell=False,  # noqa: S603
                start_new_session=True,
                close_fds=True,
            )
            _update_run(
                run_id,
                db_path=db_path,
                fields={
                    "child_pid": process.pid,
                    "phase": "running",
                    "progress": 20,
                    "heartbeat_at": utc_now_iso(),
                },
            )
            while process.poll() is None:
                current_status = _run_status(run_id, db_path=db_path)
                if current_status == "cancel_requested":
                    cancelled = True
                    _terminate_process(process)
                    break
                if time.monotonic() - started > timeout_seconds:
                    timed_out = True
                    _terminate_process(process)
                    break
                _update_run(
                    run_id,
                    db_path=db_path,
                    fields={"heartbeat_at": utc_now_iso()},
                )
                time.sleep(1)
    except Exception as exc:
        if process is not None:
            _terminate_process(process)
        now = utc_now_iso()
        _update_run(
            run_id,
            db_path=db_path,
            fields={
                "status": "failed",
                "phase": "failed",
                "progress": 100,
                "finished_at": now,
                "heartbeat_at": now,
                "error": str(exc),
            },
        )
        return get_run(run_id, db_path=db_path) or {}

    stdout = _read_tail(stdout_path)
    stderr = _read_tail(stderr_path)
    now = utc_now_iso()
    if cancelled:
        status, result, error = (
            "cancelled",
            {},
            "Run cancelled by the dashboard operator.",
        )
    elif timed_out:
        status, result, error = (
            "failed",
            {},
            f"Run exceeded its {timeout_seconds}-second safety timeout.",
        )
    else:
        returncode = process.returncode if process is not None else 1
        status, result, error = _result_from_process(
            kind=kind,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
    _update_run(
        run_id,
        db_path=db_path,
        fields={
            "status": status,
            "phase": status,
            "progress": 100,
            "finished_at": now,
            "heartbeat_at": now,
            "result_json": _json_dump(result),
            "stdout": stdout,
            "stderr": stderr,
            "error": error[:4000],
        },
    )
    return get_run(run_id, db_path=db_path) or {}


def _register_worker(*, mode: str, db_path: Path | str = DEFAULT_AUTOMATION_DB) -> str:
    init_db(db_path)
    worker_id = f"worker_{uuid4().hex}"
    now = utc_now_iso()
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO automation_workers(
              worker_id, pid, mode, status, started_at, heartbeat_at
            ) VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (worker_id, os.getpid(), mode, now, now),
        )
    return worker_id


def _worker_heartbeat(
    worker_id: str,
    *,
    status: str = "running",
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
) -> None:
    with connect(db_path) as con:
        con.execute(
            """
            UPDATE automation_workers
            SET status = ?, heartbeat_at = ?, stopped_at = CASE WHEN ? = 'stopped' THEN ? ELSE stopped_at END
            WHERE worker_id = ?
            """,
            (status, utc_now_iso(), status, utc_now_iso(), worker_id),
        )


def run_worker(
    *,
    once: bool = False,
    poll_seconds: float = 5,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    log_dir: Path | str = DEFAULT_LOG_DIR,
) -> int:
    _recover_stale_runs(db_path=db_path)
    worker_id = _register_worker(mode="once" if once else "service", db_path=db_path)
    completed = 0
    try:
        while True:
            _worker_heartbeat(worker_id, db_path=db_path)
            enqueue_due_schedule(db_path=db_path)
            run = _claim_next_run(db_path=db_path)
            if run is not None:
                execute_run(run, db_path=db_path, log_dir=log_dir)
                completed += 1
                if once:
                    break
                continue
            if once:
                break
            time.sleep(max(1.0, min(float(poll_seconds), 60.0)))
    finally:
        _worker_heartbeat(worker_id, status="stopped", db_path=db_path)
    return completed


def spawn_worker(*, db_path: Path | str = DEFAULT_AUTOMATION_DB) -> int:
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--db",
            str(Path(db_path).resolve()),
            "worker",
            "--once",
        ],
        cwd=JOB_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,  # noqa: S603
        start_new_session=True,
        close_fds=True,
    )
    return int(process.pid)




def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, indent=2))


def _parse_bool(value: str) -> bool:
    clean = value.strip().lower()
    if clean in {"1", "true", "yes", "on"}:
        return True
    if clean in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Boolean value must be true or false.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career dashboard automation worker")
    parser.add_argument("--db", type=Path, default=DEFAULT_AUTOMATION_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)

    overview = sub.add_parser("overview")
    overview.add_argument("--limit", type=int, default=30)

    detail = sub.add_parser("detail")
    detail.add_argument("--run-id", required=True)

    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--kind", required=True, choices=RUN_KINDS)
    enqueue.add_argument("--trigger", default="dashboard")
    enqueue.add_argument("--spawn-worker", action="store_true")

    retry = sub.add_parser("retry")
    retry.add_argument("--run-id", required=True)
    retry.add_argument("--spawn-worker", action="store_true")

    cancel = sub.add_parser("cancel")
    cancel.add_argument("--run-id", required=True)

    schedule = sub.add_parser("set-schedule")
    schedule.add_argument("--enabled", required=True)
    schedule.add_argument("--time", required=True)
    schedule.add_argument("--timezone", default="Europe/Vilnius")

    worker = sub.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "overview":
            data = build_overview(db_path=args.db, limit=args.limit)
        elif args.cmd == "detail":
            data = get_run(args.run_id, db_path=args.db)
            if data is None:
                raise ValueError("Automation run was not found.")
        elif args.cmd == "enqueue":
            run, created = enqueue_run(
                args.kind, trigger_source=args.trigger, db_path=args.db
            )
            worker_pid = spawn_worker(db_path=args.db) if args.spawn_worker else None
            data = {"run": run, "created": created, "worker_pid": worker_pid}
        elif args.cmd == "retry":
            run, created = retry_run(args.run_id, db_path=args.db)
            worker_pid = spawn_worker(db_path=args.db) if args.spawn_worker else None
            data = {"run": run, "created": created, "worker_pid": worker_pid}
        elif args.cmd == "cancel":
            data = {"run": cancel_run(args.run_id, db_path=args.db)}
        elif args.cmd == "set-schedule":
            data = update_schedule(
                enabled=_parse_bool(args.enabled),
                schedule_time=args.time,
                timezone_name=args.timezone,
                db_path=args.db,
            )
        elif args.cmd == "worker":
            data = {
                "completed": run_worker(
                    once=args.once,
                    poll_seconds=args.poll_seconds,
                    db_path=args.db,
                )
            }
        else:
            raise ValueError(f"Unsupported command: {args.cmd}")
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": data})
    return 0


if __name__ == "__main__":
    from career_job_search.core.entrypoint import entry
    from career_job_search.core.schema import AUTOMATION_OVERVIEW_SCHEMA

    entry(AUTOMATION_OVERVIEW_SCHEMA, main)
