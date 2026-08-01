from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from career_job_search.workspace import dashboard_service as service
from career_job_search.workspace.dashboard_service import (
    DASHBOARD_TOKEN_PLACEHOLDER,
    consume_restart_request,
    dashboard_process_environment,
    ensure_dashboard_token,
    rebuild_production_dashboard,
    service_commands,
)


def test_service_uses_fixed_argument_arrays():
    worker, dashboard = service_commands("dev", 5)

    assert worker == [
        sys.executable,
        "-m",
        "career_job_search.automation.control",
        "worker",
        "--poll-seconds",
        "5.0",
    ]
    assert dashboard == ["npm", "run", "dev"]


def test_worker_only_mode_has_no_dashboard_process():
    worker, dashboard = service_commands("worker", 0)

    assert worker[-1] == "1.0"
    assert dashboard is None


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        service_commands("public", 5)


def _dashboard_token(env_path: Path) -> str:
    prefix = "CAREER_DASHBOARD_TOKEN="
    return next(
        line[len(prefix) :]
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    )


def test_missing_dashboard_token_is_created_once_with_private_permissions(tmp_path):
    env_path = tmp_path / ".env.local"

    assert ensure_dashboard_token(env_path) is True
    first_token = _dashboard_token(env_path)
    assert len(first_token) == 64
    assert first_token != DASHBOARD_TOKEN_PLACEHOLDER
    assert env_path.stat().st_mode & 0o777 == 0o600

    assert ensure_dashboard_token(env_path) is False
    assert _dashboard_token(env_path) == first_token


def test_placeholder_token_is_replaced_without_removing_other_settings(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        f"CAREER_DASHBOARD_TOKEN={DASHBOARD_TOKEN_PLACEHOLDER}\nOTHER_SETTING=keep-me\n",
        encoding="utf-8",
    )

    assert ensure_dashboard_token(env_path) is True
    assert _dashboard_token(env_path) != DASHBOARD_TOKEN_PLACEHOLDER
    assert "OTHER_SETTING=keep-me" in env_path.read_text(encoding="utf-8")


def test_service_prefers_keychain_without_writing_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env.local"
    monkeypatch.delenv("CAREER_DASHBOARD_TOKEN", raising=False)
    monkeypatch.setattr(
        "career_job_search.workspace.dashboard_service.read_keychain_token", lambda: "keychain-secret"
    )

    environment, storage, created = dashboard_process_environment(env_path)

    assert environment["CAREER_DASHBOARD_TOKEN"] == "keychain-secret"  # noqa: S105
    assert storage == "keychain"
    assert created is False
    assert not env_path.exists()


def test_service_keeps_an_explicit_environment_secret(tmp_path, monkeypatch):
    env_path = tmp_path / ".env.local"
    monkeypatch.setattr("career_job_search.workspace.dashboard_service.read_keychain_token", lambda: "")
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "inherited-secret")

    environment, storage, created = dashboard_process_environment(env_path)

    assert environment["CAREER_DASHBOARD_TOKEN"] == "inherited-secret"  # noqa: S105
    assert storage == "environment"
    assert created is False
    assert not env_path.exists()


def test_restart_request_is_fixed_recent_and_single_use(tmp_path):
    request_path = tmp_path / "restart.json"
    now = datetime.now(UTC).replace(microsecond=0)
    request_path.write_text(
        __import__("json").dumps(
            {
                "schema": "career_dashboard_restart_request_v1",
                "command": "rebuild_restart",
                "request_id": "0123456789abcdef",
                "requested_at": (now - timedelta(seconds=2)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    assert consume_restart_request(request_path, now=now) == {
        "request_id": "0123456789abcdef",
        "requested_at": (now - timedelta(seconds=2)).isoformat(),
    }
    assert not request_path.exists()
    assert consume_restart_request(request_path, now=now) is None


def test_failed_rebuild_restores_the_previous_production_build(tmp_path, monkeypatch):
    dashboard_dir = tmp_path / "dashboard"
    old_build = dashboard_dir / ".next"
    old_build.mkdir(parents=True)
    (old_build / "BUILD_ID").write_text("old-build", encoding="utf-8")
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *_args, **_kwargs: CompletedProcess(["npm", "run", "build"], 1),
    )

    succeeded, error = rebuild_production_dashboard(dashboard_dir)

    assert succeeded is False
    assert "code 1" in error
    assert (dashboard_dir / ".next" / "BUILD_ID").read_text(encoding="utf-8") == "old-build"
    assert not (dashboard_dir / ".next.previous").exists()
