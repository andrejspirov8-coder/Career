from __future__ import annotations

import json
import subprocess
from pathlib import Path

HELPER = "src/career_job_search/recruiters/settings_helper.py"
USER_SETTINGS = Path("config/settings.yaml")
EXAMPLE_SETTINGS = Path("config/settings.example.yaml")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", HELPER, *args],
        capture_output=True, text=True, cwd=".",
    )


def test_show_returns_envelope():
    result = _run("show")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload.get("schema") == "career_python_helper_v1"
    assert payload.get("ok") is True
    assert "data" in payload


def test_show_contains_expected_sections():
    result = _run("show")
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert "runtime" in data
    assert "limits" in data
    assert "state" in data


def test_show_mode_is_valid():
    result = _run("show")
    payload = json.loads(result.stdout)
    mode = payload["data"]["runtime"]["mode"]
    assert mode in {"review_first", "automatic", "dry_run"}


def test_save_and_show_round_trip():
    backup = USER_SETTINGS.read_text(encoding="utf-8") if USER_SETTINGS.exists() else None

    try:
        modified = {
            "runtime": {"mode": "dry_run", "dry_run_default": True, "require_live_dispatch_ack": False, "require_approval_ledger": False},
            "limits": {"max_live_dispatch_batch": 1, "stop_on_captcha": True, "stop_on_checkpoint": False, "stop_on_unusual_activity": True},
            "state": {"database_path": "state/test.sqlite3", "export_csv": False},
        }
        result = _run("save", "--json", json.dumps(modified))
        assert result.returncode == 0, f"save failed: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload.get("ok") is True

        verify = _run("show")
        vpayload = json.loads(verify.stdout)
        vdata = vpayload["data"]
        assert vdata["runtime"]["mode"] == "dry_run"
        assert vdata["runtime"]["require_live_dispatch_ack"] is False
        assert vdata["limits"]["max_live_dispatch_batch"] == 1
        assert vdata["limits"]["stop_on_checkpoint"] is False
        assert vdata["state"]["export_csv"] is False
    finally:
        if backup is not None:
            USER_SETTINGS.write_text(backup, encoding="utf-8")
        elif USER_SETTINGS.exists():
            USER_SETTINGS.unlink()


def test_save_rejects_invalid_json():
    result = _run("save", "--json", "bad")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False
    assert "error" in payload


def test_save_rejects_non_object():
    result = _run("save", "--json", '"string"')
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False
    assert "error" in payload
