from __future__ import annotations

import json
import sqlite3
from pathlib import Path, PurePosixPath

import pytest

from career_job_search.workspace import control as control


def test_backup_path_allowlist_rejects_code_secrets_and_traversal():
    assert control._allowed_backup_path(PurePosixPath("state/opportunities.sqlite3"))
    assert control._allowed_backup_path(PurePosixPath("state/notifications.sqlite3"))
    assert control._allowed_backup_path(
        PurePosixPath(
            "state/cv_versions/business-process-operations/"
            "20260715T120000Z-0123456789ab.json"
        )
    )
    assert control._allowed_backup_path(PurePosixPath("output/cv.pdf"))
    assert control._allowed_backup_path(PurePosixPath("cv/assets/headshot.png"))
    assert not control._allowed_backup_path(PurePosixPath("dashboard/.env.local"))
    assert not control._allowed_backup_path(
        PurePosixPath("src/career_job_search/workspace/control.py")
    )
    assert not control._allowed_backup_path(PurePosixPath("state/../.env"))
    assert not control._allowed_backup_path(
        PurePosixPath("state/dashboard_service.json")
    )
    assert not control._allowed_backup_path(
        PurePosixPath("state/dashboard_restart.request.json")
    )


def test_managed_restart_request_requires_a_fresh_production_supervisor(
    tmp_path, monkeypatch
):
    status_path = tmp_path / "dashboard_service.json"
    request_path = tmp_path / "dashboard_restart.request.json"
    status_path.write_text(
        json.dumps(
            {
                "schema": "career_dashboard_service_v1",
                "pid": 321,
                "mode": "production",
                "status": "running",
                "heartbeat_at": control.utc_now_iso(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(control, "DASHBOARD_SERVICE_STATUS_PATH", status_path)
    monkeypatch.setattr(control, "DASHBOARD_RESTART_REQUEST_PATH", request_path)
    monkeypatch.setattr(control, "_process_alive", lambda pid: pid == 321)

    result = control.request_dashboard_restart()
    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert result["requested"] is True
    assert request["command"] == "rebuild_restart"
    assert request["request_id"] == result["request_id"]
    assert request_path.stat().st_mode & 0o777 == 0o600


def test_managed_restart_request_rejects_an_unmanaged_server(tmp_path, monkeypatch):
    monkeypatch.setattr(
        control, "DASHBOARD_SERVICE_STATUS_PATH", tmp_path / "missing-status.json"
    )

    with pytest.raises(RuntimeError, match="make dashboard-start"):
        control.request_dashboard_restart()


def test_dashboard_runtime_status_reports_source_freshness_and_supervisor(
    tmp_path, monkeypatch
):
    dashboard = tmp_path / "dashboard"
    app = dashboard / "app"
    app.mkdir(parents=True)
    (app / "page.tsx").write_text(
        "export default function Page() {}\n", encoding="utf-8"
    )
    status_path = tmp_path / "state" / "dashboard_service.json"
    status_path.parent.mkdir()
    status_path.write_text(
        json.dumps(
            {
                "schema": "career_dashboard_service_v1",
                "pid": 654,
                "mode": "production",
                "status": "running",
                "heartbeat_at": control.utc_now_iso(),
                "last_update": {"status": "failed", "error": "safe test failure"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(control, "DASHBOARD_DIR", dashboard)
    monkeypatch.setattr(control, "DASHBOARD_SERVICE_STATUS_PATH", status_path)
    monkeypatch.setattr(control, "_process_alive", lambda pid: pid == 654)

    result = control.dashboard_runtime_status()

    assert result["restart_supported"] is True
    assert result["latest_source_modified_at"]
    assert result["last_restart_error"] == "safe test failure"


def test_env_token_can_move_to_keychain_without_leaking_other_settings(
    tmp_path, monkeypatch
):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "CAREER_DASHBOARD_TOKEN=private-value\nOTHER_SETTING=keep-me\n",
        encoding="utf-8",
    )
    stored: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(control, "DASHBOARD_ENV_PATH", env_path)
    monkeypatch.setattr(control, "keychain_supported", lambda: True)
    monkeypatch.setattr(control, "read_keychain_token", lambda: "")
    monkeypatch.setattr(
        control,
        "_run",
        lambda command, **_kwargs: (
            stored.append((command, _kwargs))
            or __import__("subprocess").CompletedProcess(command, 0, "", "")
        ),
    )

    result = control.enable_keychain()

    assert result == {"configured": True, "storage": "keychain"}
    assert "CAREER_DASHBOARD_TOKEN" not in env_path.read_text(encoding="utf-8")
    assert "OTHER_SETTING=keep-me" in env_path.read_text(encoding="utf-8")
    assert stored and stored[0][0][-1] == "-w"
    assert "private-value" not in stored[0][0]
    assert stored[0][1]["input_text"] == "private-value\n"


def test_launch_agent_uses_fixed_arguments_and_local_project_path(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(control.shutil, "which", lambda name: f"/safe/bin/{name}")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    payload = control._launch_agent_payload()

    assert payload["ProgramArguments"][0] == "/safe/bin/uv"
    assert payload["ProgramArguments"][1:5] == [
        "run",
        "python",
        "-m",
        "career_job_search.workspace.dashboard_service",
    ]
    assert payload["WorkingDirectory"] == str(control.JOB_ROOT)
    assert payload["RunAtLoad"] is True
    assert payload["ThrottleInterval"] == 30
    assert "--hostname" not in " ".join(payload["ProgramArguments"])


def test_encrypted_backup_round_trip_and_wrong_passphrase(tmp_path, monkeypatch):
    job_root = tmp_path / "job-search"
    state = job_root / "state"
    output = job_root / "output"
    state.mkdir(parents=True)
    output.mkdir()
    (state / "application_workspace.json").write_text(
        '{"entries": {}}\n', encoding="utf-8"
    )
    (output / "cv.pdf").write_bytes(b"%PDF-safe-test")
    database = state / "opportunities.sqlite3"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE sample(value TEXT)")
        con.execute("INSERT INTO sample VALUES ('kept')")

    monkeypatch.setattr(control, "JOB_ROOT", job_root)
    monkeypatch.setattr(control, "BACKUP_DIR", state / "backups")

    created = control.create_backup("correct horse battery staple")
    validated = control.validate_backup(
        created["filename"], "correct horse battery staple"
    )

    assert created["file_count"] == 3
    assert validated["valid"] is True
    encrypted = (control.BACKUP_DIR / created["filename"]).read_bytes()
    assert b"kept" not in encrypted
    assert b"application_workspace" not in encrypted
    with pytest.raises(ValueError, match="wrong or the file is damaged"):
        control.validate_backup(created["filename"], "this is the wrong passphrase")


def test_restore_requires_confirmation_and_offline_worker(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    filename = "career-backup-20260715T120000Z-abcdef.career-backup"
    (backup_dir / filename).write_bytes(b"placeholder")
    monkeypatch.setattr(control, "BACKUP_DIR", backup_dir)

    with pytest.raises(ValueError, match="Type RESTORE exactly"):
        control.restore_backup(filename, "correct horse battery staple", "restore")

    monkeypatch.setattr(control, "_worker_online", lambda: True)
    with pytest.raises(RuntimeError, match="Stop the dashboard automation worker"):
        control.restore_backup(filename, "correct horse battery staple", "RESTORE")


def test_restore_rejects_unsafe_archive_member(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    import io
    import tarfile

    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("../outside.txt")
        content = b"unsafe"
        info.size = len(content)
        handle.addfile(info, io.BytesIO(content))

    with pytest.raises(ValueError, match="unsafe path"):
        control._extract_and_validate_archive(archive, tmp_path / "extract")


def test_restore_rejects_unlisted_archive_files(tmp_path):
    archive = tmp_path / "extra.tar.gz"
    import io
    import tarfile

    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("extra.txt")
        content = b"unexpected"
        info.size = len(content)
        handle.addfile(info, io.BytesIO(content))

    with pytest.raises(ValueError, match="unexpected file"):
        control._extract_and_validate_archive(archive, tmp_path / "extract")


def test_json_payload_rejects_large_or_non_object_input(monkeypatch):
    class Input:
        def read(self, _size: int) -> bytes:
            return json.dumps(["not", "an", "object"]).encode()

    monkeypatch.setattr(control.sys, "stdin", type("Stdin", (), {"buffer": Input()})())
    with pytest.raises(ValueError, match="must be an object"):
        control._read_payload()
