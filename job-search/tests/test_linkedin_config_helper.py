from __future__ import annotations

import json
import subprocess
from pathlib import Path

HELPER = "src/career_job_search/integrations/linkedin/config_helper.py"
LINKEDIN_CONFIG = Path("linkedin/config.yaml")


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


def test_show_contains_expected_keys():
    result = _run("show")
    payload = json.loads(result.stdout)
    data = payload["data"]
    expected = {"linkedin_base_url", "browser", "limits", "matching", "llm", "search"}
    for key in expected:
        assert key in data, f"Missing top-level key: {key}"


def test_save_and_show_round_trip():
    backup = None
    if LINKEDIN_CONFIG.exists():
        backup = LINKEDIN_CONFIG.read_text(encoding="utf-8")

    try:
        minimal = {
            "linkedin_base_url": "https://www.linkedin.com",
            "browser": {"channel": "chrome", "backend": "playwright", "debug_port": 9222, "headless": True},
            "limits": {"max_connections": 5, "min_delay_seconds": 30, "max_delay_seconds": 90, "daily_cap": 20},
            "matching": {"min_primary_score": 6, "require_recruiter_gate": False, "cv_min_scores": {}},
            "llm": {"provider": "ollama", "model": "qwen3.5:35b", "profiles": {}},
            "automation": {"max_live_dispatch": 3, "require_llm_note": True},
        }
        result = _run("save", "--json", json.dumps(minimal))
        assert result.returncode == 0, f"save failed: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload.get("ok") is True

        verify = _run("show")
        vpayload = json.loads(verify.stdout)
        vdata = vpayload["data"]
        assert vdata["linkedin_base_url"] == "https://www.linkedin.com"
        assert vdata["browser"]["channel"] == "chrome"
        assert vdata["browser"]["headless"] is True
        assert vdata["limits"]["daily_cap"] == 20
        assert vdata["llm"]["provider"] == "ollama"
        assert vdata["automation"]["max_live_dispatch"] == 3
    finally:
        if backup is not None:
            LINKEDIN_CONFIG.write_text(backup, encoding="utf-8")
        elif LINKEDIN_CONFIG.exists():
            LINKEDIN_CONFIG.unlink()


def test_save_rejects_invalid_json():
    result = _run("save", "--json", "bad json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False
    assert "error" in payload


def test_save_rejects_non_object():
    result = _run("save", "--json", '"just a string"')
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False
    assert "error" in payload
