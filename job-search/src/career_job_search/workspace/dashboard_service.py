#!/usr/bin/env python3
"""Run the local dashboard and its automation worker as one service."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT
from career_job_search.workspace.control import read_env_token, read_keychain_token

DASHBOARD_DIR = JOB_ROOT / "dashboard"
AUTOMATION_CONTROL = JOB_ROOT / "tools" / "automation_control.py"
LOCAL_DEV_AGENTS = JOB_ROOT / "tools" / "local_dev_agents.py"
DASHBOARD_TOKEN_KEY = "CAREER_DASHBOARD_TOKEN"
DASHBOARD_TOKEN_PLACEHOLDER = "replace-with-a-long-random-local-token"
SERVICE_STATUS_PATH = JOB_ROOT / "state" / "dashboard_service.json"
RESTART_REQUEST_PATH = JOB_ROOT / "state" / "dashboard_restart.request.json"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _write_private_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _write_service_status(
    *,
    mode: str,
    started_at: str,
    status: str,
    phase: str,
    last_update: dict[str, object] | None,
) -> None:
    _write_private_json(
        SERVICE_STATUS_PATH,
        {
            "schema": "career_dashboard_service_v1",
            "pid": os.getpid(),
            "mode": mode,
            "status": status,
            "phase": phase,
            "started_at": started_at,
            "heartbeat_at": utc_now_iso(),
            "last_update": last_update,
        },
    )


def _remove_owned_service_status() -> None:
    try:
        payload = json.loads(SERVICE_STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if isinstance(payload, dict) and payload.get("pid") == os.getpid():
        SERVICE_STATUS_PATH.unlink(missing_ok=True)


def consume_restart_request(
    path: Path = RESTART_REQUEST_PATH,
    *,
    now: datetime | None = None,
) -> dict[str, str] | None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return None
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    path.unlink(missing_ok=True)
    if len(raw) > 16 * 1024:
        return None
    try:
        payload = json.loads(raw)
        requested_at = datetime.fromisoformat(str(payload.get("requested_at")))
        request_id = str(payload.get("request_id") or "")
    except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if requested_at.tzinfo is None:
        return None
    age = ((now or datetime.now(UTC)) - requested_at).total_seconds()
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "career_dashboard_restart_request_v1"
        or payload.get("command") != "rebuild_restart"
        or len(request_id) != 16
        or any(character not in "0123456789abcdef" for character in request_id)
        or not 0 <= age <= 300
    ):
        return None
    return {"request_id": request_id, "requested_at": requested_at.isoformat()}


def rebuild_production_dashboard(
    dashboard_dir: Path = DASHBOARD_DIR,
    *,
    environment: dict[str, str] | None = None,
) -> tuple[bool, str]:
    build_dir = dashboard_dir / ".next"
    previous_dir = dashboard_dir / ".next.previous"
    if previous_dir.exists():
        shutil.rmtree(previous_dir)
    if build_dir.exists():
        os.replace(build_dir, previous_dir)
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=dashboard_dir,
            env=environment,
            shell=False,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Build exited with code {result.returncode}.")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        if build_dir.exists():
            shutil.rmtree(build_dir)
        if previous_dir.exists():
            os.replace(previous_dir, build_dir)
        return False, str(exc)
    if previous_dir.exists():
        shutil.rmtree(previous_dir)
    return True, ""


def ensure_dashboard_token(env_path: Path = DASHBOARD_DIR / ".env.local") -> bool:
    """Create a private local token when configuration is absent or placeholder-only."""

    existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = existing_text.splitlines()
    token_prefix = f"{DASHBOARD_TOKEN_KEY}="
    token_index = next(
        (index for index, line in enumerate(lines) if line.startswith(token_prefix)),
        None,
    )
    current_token = (
        lines[token_index][len(token_prefix) :].strip()
        if token_index is not None
        else ""
    )

    if current_token and current_token != DASHBOARD_TOKEN_PLACEHOLDER:
        os.chmod(env_path, 0o600)
        return False

    replacement = f"{token_prefix}{secrets.token_hex(32)}"
    if token_index is None:
        lines.append(replacement)
    else:
        lines[token_index] = replacement
    rendered = "\n".join(lines).rstrip("\n") + "\n"

    env_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=env_path.parent,
            prefix=f".{env_path.name}.",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, env_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return True


def dashboard_process_environment(
    env_path: Path = DASHBOARD_DIR / ".env.local",
) -> tuple[dict[str, str], str, bool]:
    """Resolve the secret without exposing it to the command line or logs."""

    environment = os.environ.copy()
    keychain_token = read_keychain_token()
    if keychain_token:
        environment[DASHBOARD_TOKEN_KEY] = keychain_token
        return environment, "keychain", False

    inherited_token = environment.get(DASHBOARD_TOKEN_KEY, "").strip()
    if inherited_token and inherited_token != DASHBOARD_TOKEN_PLACEHOLDER:
        return environment, "environment", False

    created = ensure_dashboard_token(env_path)
    file_token = read_env_token(env_path)
    if not file_token:
        raise RuntimeError("The private dashboard login secret could not be prepared.")
    environment[DASHBOARD_TOKEN_KEY] = file_token
    return environment, "env_file", created


def service_commands(
    mode: str, poll_seconds: float
) -> tuple[list[str], list[str] | None]:
    worker = [
        sys.executable,
        str(AUTOMATION_CONTROL),
        "worker",
        "--poll-seconds",
        str(max(1.0, min(float(poll_seconds), 60.0))),
    ]
    if mode == "worker":
        return worker, None
    if mode == "production":
        return worker, ["npm", "run", "start"]
    if mode == "dev":
        return worker, ["npm", "run", "dev"]
    raise ValueError(f"Unsupported dashboard service mode: {mode}")


def development_agent_command(poll_seconds: float) -> list[str]:
    return [
        sys.executable,
        str(LOCAL_DEV_AGENTS),
        "service",
        "--poll-seconds",
        str(max(1.0, min(float(poll_seconds), 60.0))),
    ]


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=7)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait(timeout=5)


def run_service(mode: str, *, poll_seconds: float = 5) -> int:
    worker_command, dashboard_command = service_commands(mode, poll_seconds)
    development_command = development_agent_command(poll_seconds)
    dashboard_environment: dict[str, str] | None = None
    if dashboard_command is not None:
        dashboard_environment, token_storage, created = dashboard_process_environment()
        if created:
            print(
                "Created dashboard/.env.local with a private dashboard login secret.",
                file=sys.stderr,
            )
        elif token_storage == "keychain":
            print(
                "Loaded the dashboard login secret from macOS Keychain.",
                file=sys.stderr,
            )
    if mode == "production" and not (DASHBOARD_DIR / ".next" / "BUILD_ID").exists():
        raise RuntimeError(
            "Production dashboard is not built. Run: make dashboard-build"
        )

    worker: subprocess.Popen[bytes] | None = None
    development_agent: subprocess.Popen[bytes] | None = None
    dashboard: subprocess.Popen[bytes] | None = None
    stopping = False
    started_at = utc_now_iso()
    last_update: dict[str, object] | None = None

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    previous_handlers = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    for signum in previous_handlers:
        signal.signal(signum, request_stop)

    try:
        worker = subprocess.Popen(
            worker_command,
            cwd=JOB_ROOT,
            shell=False,
            start_new_session=True,
            close_fds=True,
        )
        development_agent = subprocess.Popen(
            development_command,
            cwd=JOB_ROOT,
            shell=False,
            start_new_session=True,
            close_fds=True,
        )
        if dashboard_command is None:
            while not stopping:
                worker_code = worker.poll()
                development_code = development_agent.poll()
                if worker_code is not None:
                    return int(worker_code)
                if development_code is not None:
                    raise RuntimeError(
                        "Development-agent service stopped unexpectedly with "
                        f"exit code {development_code}."
                    )
                time.sleep(0.5)
            return 0

        dashboard = subprocess.Popen(
            dashboard_command,
            cwd=DASHBOARD_DIR,
            env=dashboard_environment,
            shell=False,
            start_new_session=True,
            close_fds=True,
        )
        _write_service_status(
            mode=mode,
            started_at=started_at,
            status="running",
            phase="ready",
            last_update=last_update,
        )
        last_heartbeat = time.monotonic()
        while not stopping:
            if time.monotonic() - last_heartbeat >= 2:
                _write_service_status(
                    mode=mode,
                    started_at=started_at,
                    status="running",
                    phase="ready",
                    last_update=last_update,
                )
                last_heartbeat = time.monotonic()

            restart_request = consume_restart_request() if mode == "production" else None
            if restart_request is not None:
                _write_service_status(
                    mode=mode,
                    started_at=started_at,
                    status="updating",
                    phase="rebuilding",
                    last_update=last_update,
                )
                _terminate(dashboard)
                dashboard = None
                rebuilt, build_error = rebuild_production_dashboard(
                    environment=dashboard_environment
                )
                last_update = {
                    "request_id": restart_request["request_id"],
                    "status": "succeeded" if rebuilt else "failed",
                    "finished_at": utc_now_iso(),
                    "error": build_error,
                }
                dashboard = subprocess.Popen(
                    dashboard_command,
                    cwd=DASHBOARD_DIR,
                    env=dashboard_environment,
                    shell=False,
                    start_new_session=True,
                    close_fds=True,
                )
                _write_service_status(
                    mode=mode,
                    started_at=started_at,
                    status="running",
                    phase="ready",
                    last_update=last_update,
                )
                last_heartbeat = time.monotonic()
                continue

            dashboard_code = dashboard.poll()
            worker_code = worker.poll()
            development_code = development_agent.poll()
            if dashboard_code is not None:
                return int(dashboard_code)
            if worker_code is not None:
                raise RuntimeError(
                    f"Automation worker stopped unexpectedly with exit code {worker_code}."
                )
            if development_code is not None:
                raise RuntimeError(
                    "Development-agent service stopped unexpectedly with "
                    f"exit code {development_code}."
                )
            time.sleep(0.5)
        return 0
    finally:
        _terminate(dashboard)
        _terminate(development_agent)
        _terminate(worker)
        _remove_owned_service_status()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career dashboard local service")
    parser.add_argument(
        "--mode",
        choices=("dev", "production", "worker"),
        default="dev",
    )
    parser.add_argument("--poll-seconds", type=float, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_service(args.mode, poll_seconds=args.poll_seconds)
    except Exception as exc:
        print(f"Dashboard service failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
