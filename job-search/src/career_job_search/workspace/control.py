#!/usr/bin/env python3
"""Safe local controls for dashboard secrets, startup, and encrypted backups.

The web dashboard calls only the fixed commands exposed by this module. Secret
values arrive through standard input, never through command-line arguments,
and are never returned in JSON responses.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import project_path
from career_job_search.workspace import backups as _backups

JOB_ROOT = project_path()
DASHBOARD_DIR = JOB_ROOT / "dashboard"
DASHBOARD_ENV_PATH = DASHBOARD_DIR / ".env.local"
DASHBOARD_TOKEN_KEY = "CAREER_DASHBOARD_TOKEN"
DASHBOARD_TOKEN_PLACEHOLDER = "replace-with-a-long-random-local-token"
KEYCHAIN_SERVICE = "com.andrejspirov.career.dashboard"
KEYCHAIN_ACCOUNT = getpass.getuser()
SECURITY_BIN = Path("/usr/bin/security")
LAUNCHCTL_BIN = Path("/bin/launchctl")
LAUNCH_AGENT_LABEL = "com.andrejspirov.career-dashboard"
LAUNCH_AGENT_PATH = (
    Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
)
BACKUP_DIR = JOB_ROOT / "state" / "backups"
DASHBOARD_SERVICE_STATUS_PATH = JOB_ROOT / "state" / "dashboard_service.json"
DASHBOARD_RESTART_REQUEST_PATH = JOB_ROOT / "state" / "dashboard_restart.request.json"
BACKUP_FILENAME_PATTERN = re.compile(
    r"^career-(?:backup|pre-restore)-\d{8}T\d{6}Z(?:-[a-f0-9]{6})?\.career-backup$"
)
BACKUP_MAGIC = b"CAREER_BACKUP_V1\n"
BACKUP_SCHEMA = "career_encrypted_backup_v1"
MAX_INPUT_BYTES = 8 * 1024
MAX_BACKUP_BYTES = 300 * 1024 * 1024
MAX_BACKUP_FILES = 5_000
MIN_PASSPHRASE_LENGTH = 12
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
DASHBOARD_RUNTIME_EXTENSIONS = {".css", ".js", ".json", ".mjs", ".ts", ".tsx"}
DASHBOARD_RUNTIME_FILES = {
    "app.css",
    "next.config.mjs",
    "package.json",
    "package-lock.json",
    "proxy.ts",
    "tsconfig.json",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
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


def _read_small_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise RuntimeError("The local service status path is unsafe.")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    if len(raw) > 16 * 1024:
        raise RuntimeError("The local service status is invalid.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The local service status is invalid.") from exc
    return value if isinstance(value, dict) else {}


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _fresh_production_service_status(status: dict[str, Any]) -> bool:
    try:
        pid = int(status.get("pid"))
        heartbeat = datetime.fromisoformat(str(status.get("heartbeat_at")))
        if heartbeat.tzinfo is None:
            return False
    except (TypeError, ValueError):
        return False
    age = (datetime.now(UTC) - heartbeat).total_seconds()
    return (
        status.get("schema") == "career_dashboard_service_v1"
        and status.get("mode") == "production"
        and status.get("status") == "running"
        and pid >= 2
        and 0 <= age <= 15
        and _process_alive(pid)
    )


def _latest_dashboard_source_modified_at() -> str:
    candidates: list[Path] = []
    for directory in (DASHBOARD_DIR / "app", DASHBOARD_DIR / "lib"):
        if directory.is_dir():
            candidates.extend(path for path in directory.rglob("*") if path.is_file())
    candidates.extend(DASHBOARD_DIR / name for name in DASHBOARD_RUNTIME_FILES)
    latest = 0.0
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        if path.suffix.lower() not in DASHBOARD_RUNTIME_EXTENSIONS:
            continue
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return datetime.fromtimestamp(latest, UTC).isoformat() if latest else ""


def dashboard_runtime_status() -> dict[str, Any]:
    try:
        service = _read_small_json(DASHBOARD_SERVICE_STATUS_PATH)
    except RuntimeError:
        service = {}
    last_error = ""
    last_update = service.get("last_update")
    if isinstance(last_update, dict) and last_update.get("status") == "failed":
        error = last_update.get("error")
        if isinstance(error, str):
            last_error = " ".join(error.split())[:300]
    return {
        "latest_source_modified_at": _latest_dashboard_source_modified_at(),
        "restart_supported": _fresh_production_service_status(service),
        "last_restart_error": last_error,
    }


def request_dashboard_restart() -> dict[str, Any]:
    status = _read_small_json(DASHBOARD_SERVICE_STATUS_PATH)
    if not _fresh_production_service_status(status):
        raise RuntimeError(
            "Managed restart is unavailable. Start the app with: make dashboard-start"
        )
    request_id = secrets.token_hex(8)
    _write_private_json(
        DASHBOARD_RESTART_REQUEST_PATH,
        {
            "schema": "career_dashboard_restart_request_v1",
            "command": "rebuild_restart",
            "request_id": request_id,
            "requested_at": utc_now_iso(),
        },
    )
    return {
        "requested": True,
        "request_id": request_id,
        "message": "The dashboard will rebuild and restart locally.",
    }


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 20,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        shell=False,
        timeout=timeout,
        check=False,
    )


def _env_lines(env_path: Path | None = None) -> list[str]:
    env_path = env_path or DASHBOARD_ENV_PATH
    try:
        return env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []


def read_env_token(env_path: Path | None = None) -> str:
    env_path = env_path or DASHBOARD_ENV_PATH
    prefix = f"{DASHBOARD_TOKEN_KEY}="
    for line in _env_lines(env_path):
        if line.startswith(prefix):
            token = line[len(prefix) :].strip()
            if token and token != DASHBOARD_TOKEN_PLACEHOLDER:
                return token
    return ""


def _write_env_token(token: str | None, env_path: Path | None = None) -> None:
    env_path = env_path or DASHBOARD_ENV_PATH
    prefix = f"{DASHBOARD_TOKEN_KEY}="
    lines = [line for line in _env_lines(env_path) if not line.startswith(prefix)]
    if token:
        lines.append(f"{prefix}{token}")
    rendered = "\n".join(lines).rstrip("\n")
    if rendered:
        rendered += "\n"

    env_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=env_path.parent,
            prefix=f".{env_path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, env_path)
        env_path.chmod(0o600)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def keychain_supported() -> bool:
    return sys.platform == "darwin" and SECURITY_BIN.is_file()


def read_keychain_token() -> str:
    if not keychain_supported():
        return ""
    result = _run(
        [
            str(SECURITY_BIN),
            "find-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ]
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def enable_keychain() -> dict[str, Any]:
    if not keychain_supported():
        raise RuntimeError("macOS Keychain is not available on this computer.")
    token = read_keychain_token() or os.environ.get(DASHBOARD_TOKEN_KEY, "").strip()
    token = token or read_env_token()
    if not token or token == DASHBOARD_TOKEN_PLACEHOLDER:
        token = secrets.token_hex(32)
    result = _run(
        [
            str(SECURITY_BIN),
            "add-generic-password",
            "-U",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        input_text=f"{token}\n",
    )
    if result.returncode != 0:
        raise RuntimeError("The dashboard secret could not be stored in Keychain.")
    _write_env_token(None)
    return {"configured": True, "storage": "keychain"}


def disable_keychain() -> dict[str, Any]:
    token = read_keychain_token()
    if not token:
        return {
            "configured": bool(read_env_token()),
            "storage": "env_file" if read_env_token() else "missing",
        }
    _write_env_token(token)
    result = _run(
        [
            str(SECURITY_BIN),
            "delete-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(
            "The secret was copied to the private settings file, but the Keychain item could not be removed."
        )
    return {"configured": True, "storage": "env_file"}


def keychain_status() -> dict[str, Any]:
    in_keychain = bool(read_keychain_token())
    in_process = bool(os.environ.get(DASHBOARD_TOKEN_KEY, "").strip())
    in_file = bool(read_env_token())
    storage = (
        "keychain"
        if in_keychain
        else "env_file" if in_file else "environment" if in_process else "missing"
    )
    return {
        "supported": keychain_supported(),
        "configured": in_keychain or in_process or in_file,
        "storage": storage,
    }


def _launch_agent_target() -> str:
    return f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"


def _launch_agent_loaded() -> bool:
    if sys.platform != "darwin" or not LAUNCHCTL_BIN.is_file():
        return False
    result = _run([str(LAUNCHCTL_BIN), "print", _launch_agent_target()])
    return result.returncode == 0


def _launch_agent_payload() -> dict[str, Any]:
    uv_path = shutil.which("uv")
    npm_path = shutil.which("npm")
    if not uv_path or not npm_path:
        raise RuntimeError(
            "uv and npm must be installed before startup can be enabled."
        )
    path_dirs = {
        str(Path(uv_path).parent),
        str(Path(npm_path).parent),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    }
    log_dir = Path.home() / "Library" / "Logs" / "CareerDashboard"
    log_dir.mkdir(parents=True, exist_ok=True)
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            uv_path,
            "run",
            "python",
            str(JOB_ROOT / "tools" / "dashboard_service.py"),
            "--mode",
            "production",
        ],
        "WorkingDirectory": str(JOB_ROOT),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "ProcessType": "Interactive",
        "EnvironmentVariables": {"PATH": ":".join(sorted(path_dirs))},
        "StandardOutPath": str(log_dir / "service.stdout.log"),
        "StandardErrorPath": str(log_dir / "service.stderr.log"),
    }


def enable_startup() -> dict[str, Any]:
    if sys.platform != "darwin":
        raise RuntimeError("Automatic sign-in startup is available only on macOS.")
    if not (DASHBOARD_DIR / ".next" / "BUILD_ID").is_file():
        raise RuntimeError("Build the production dashboard before enabling startup.")
    if not keychain_status()["configured"]:
        raise RuntimeError(
            "Configure the dashboard login secret before enabling startup."
        )
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=LAUNCH_AGENT_PATH.parent,
            prefix=f".{LAUNCH_AGENT_PATH.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            plistlib.dump(_launch_agent_payload(), handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, LAUNCH_AGENT_PATH)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return startup_status()


def disable_startup() -> dict[str, Any]:
    if _launch_agent_loaded():
        result = _run(
            [str(LAUNCHCTL_BIN), "bootout", _launch_agent_target()], timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError("The automatic startup service could not be stopped.")
    LAUNCH_AGENT_PATH.unlink(missing_ok=True)
    return startup_status()


def startup_status() -> dict[str, Any]:
    return {
        "supported": sys.platform == "darwin",
        "installed": LAUNCH_AGENT_PATH.is_file(),
        "loaded": _launch_agent_loaded(),
        "path": str(LAUNCH_AGENT_PATH),
    }


_allowed_backup_path = _backups._allowed_backup_path
_extract_and_validate_archive = _backups._extract_and_validate_archive
_validate_passphrase = _backups._validate_passphrase


def create_backup(passphrase: str, *, pre_restore: bool = False) -> dict[str, Any]:
    return _backups.create_backup(
        passphrase,
        pre_restore=pre_restore,
        job_root=JOB_ROOT,
        backup_dir=BACKUP_DIR,
    )


def list_backups() -> list[dict[str, Any]]:
    return _backups.list_backups(BACKUP_DIR)


def validate_backup(filename: str, passphrase: str) -> dict[str, Any]:
    return _backups.validate_backup(
        filename,
        passphrase,
        backup_dir=BACKUP_DIR,
    )


def _worker_online() -> bool:
    return _backups._worker_online(JOB_ROOT)


def restore_backup(
    filename: str, passphrase: str, confirmation: str
) -> dict[str, Any]:
    return _backups.restore_backup(
        filename,
        passphrase,
        confirmation,
        job_root=JOB_ROOT,
        backup_dir=BACKUP_DIR,
        worker_online_check=_worker_online,
    )


def workspace_status() -> dict[str, Any]:
    return {
        "schema": "career_workspace_controls_v1",
        "generated_at": utc_now_iso(),
        "dashboard_runtime": dashboard_runtime_status(),
        "keychain": keychain_status(),
        "startup": startup_status(),
        "backup": {
            "supported": True,
            "directory": str(BACKUP_DIR),
            "minimum_passphrase_length": MIN_PASSPHRASE_LENGTH,
            "restore_available": not _worker_online(),
            "backups": list_backups(),
        },
    }


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("The control request is too large.")
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("The control request is invalid.") from exc
    if not isinstance(payload, dict):
        raise ValueError("The control request must be an object.")
    return payload


def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career workspace local controls")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for command in (
        "status",
        "keychain-enable",
        "keychain-disable",
        "startup-enable",
        "startup-disable",
        "backup-create",
        "backup-validate",
        "backup-restore",
        "dashboard-restart",
        "backup-create-interactive",
    ):
        sub.add_parser(command)
    validate_interactive = sub.add_parser("backup-validate-interactive")
    validate_interactive.add_argument("--filename", required=True)
    restore_interactive = sub.add_parser("backup-restore-interactive")
    restore_interactive.add_argument("--filename", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "status":
            data = workspace_status()
        elif args.cmd == "keychain-enable":
            data = enable_keychain()
        elif args.cmd == "keychain-disable":
            data = disable_keychain()
        elif args.cmd == "startup-enable":
            data = enable_startup()
        elif args.cmd == "startup-disable":
            data = disable_startup()
        elif args.cmd == "dashboard-restart":
            data = request_dashboard_restart()
        elif args.cmd == "backup-create-interactive":
            data = create_backup(getpass.getpass("Backup passphrase: "))
        elif args.cmd == "backup-validate-interactive":
            data = validate_backup(
                args.filename, getpass.getpass("Backup passphrase: ")
            )
        elif args.cmd == "backup-restore-interactive":
            passphrase = getpass.getpass("Backup passphrase: ")
            confirmation = input("Type RESTORE to confirm recovery: ").strip()
            data = restore_backup(args.filename, passphrase, confirmation)
        else:
            payload = _read_payload()
            passphrase = _validate_passphrase(payload.get("passphrase"))
            if args.cmd == "backup-create":
                data = create_backup(passphrase)
            elif args.cmd == "backup-validate":
                data = validate_backup(str(payload.get("filename") or ""), passphrase)
            elif args.cmd == "backup-restore":
                data = restore_backup(
                    str(payload.get("filename") or ""),
                    passphrase,
                    str(payload.get("confirmation") or ""),
                )
            else:
                raise ValueError("Unsupported workspace control command.")
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": data})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
