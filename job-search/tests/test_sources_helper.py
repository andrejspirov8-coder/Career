from __future__ import annotations

import json
import subprocess
from pathlib import Path

HELPER = "src/career_job_search/opportunities/sources_helper.py"
USER_CONFIG = Path("config/opportunities.yaml")
EXAMPLE_CONFIG = Path("config/opportunities.example.yaml")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", HELPER, *args],
        capture_output=True,
        text=True,
        cwd=".",
    )


def test_show_returns_envelope():
    result = _run("show")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload.get("schema") == "career_python_helper_v1"
    assert payload.get("ok") is True
    assert "data" in payload
    assert "opportunities" in payload["data"]


def test_show_contains_sources():
    backup = None
    if USER_CONFIG.exists():
        backup = USER_CONFIG.read_text(encoding="utf-8")
        USER_CONFIG.unlink()

    try:
        result = _run("show")
        payload = json.loads(result.stdout)
        sources = payload["data"]["opportunities"].get("sources", {})
        expected = {"inbox", "company_watchlist", "linkedin", "ats", "cvmarket_rss"}
        for name in expected:
            assert name in sources, f"Missing source: {name}"
            assert "enabled" in sources[name], f"Source {name} missing enabled flag"
    finally:
        if backup is not None:
            USER_CONFIG.write_text(backup, encoding="utf-8")


def test_show_defaults_returns_envelope():
    result = _run("show-defaults")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True
    assert "data" in payload


def test_save_and_show_round_trip():
    backup = None
    if USER_CONFIG.exists():
        backup = USER_CONFIG.read_text(encoding="utf-8")

    try:
        minimal = {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": True, "path": "inbox/test"},
                    "cvmarket_rss": {
                        "enabled": False,
                        "feed_url": "https://example.com/rss",
                    },
                },
            },
        }
        result = _run("save", "--json", json.dumps(minimal))
        assert result.returncode == 0, f"save failed: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload.get("ok") is True

        verify = _run("show")
        vpayload = json.loads(verify.stdout)
        vsources = vpayload["data"]["opportunities"]["sources"]
        assert vsources["inbox"]["enabled"] is True
        assert vsources["inbox"]["path"] == "inbox/test"
        assert vsources["cvmarket_rss"]["enabled"] is False

        assert USER_CONFIG.exists()
    finally:
        if backup is not None:
            USER_CONFIG.write_text(backup, encoding="utf-8")
        elif USER_CONFIG.exists():
            USER_CONFIG.unlink()


def test_save_rejects_invalid_json():
    result = _run("save", "--json", "not valid json")
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


def test_show_reads_user_config_over_example():
    backup = None
    if USER_CONFIG.exists():
        backup = USER_CONFIG.read_text(encoding="utf-8")

    try:
        custom = {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": False, "path": "custom/path"},
                },
            },
        }
        _run("save", "--json", json.dumps(custom))

        result = _run("show")
        payload = json.loads(result.stdout)
        assert payload["data"]["opportunities"]["sources"]["inbox"]["enabled"] is False
        assert (
            payload["data"]["opportunities"]["sources"]["inbox"]["path"]
            == "custom/path"
        )
    finally:
        if backup is not None:
            USER_CONFIG.write_text(backup, encoding="utf-8")
        elif USER_CONFIG.exists():
            USER_CONFIG.unlink()
