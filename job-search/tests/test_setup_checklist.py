from __future__ import annotations

import json
import subprocess

HELPER = "src/career_job_search/setup/checklist.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", HELPER, *args],
        capture_output=True, text=True, cwd=".",
    )


def test_check_returns_envelope():
    result = _run("check")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload.get("schema") == "career_python_helper_v1"
    assert payload.get("ok") is True
    assert "data" in payload


def test_check_contains_steps():
    result = _run("check")
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert "steps" in data
    assert len(data["steps"]) >= 4
    assert "done_count" in data
    assert "total" in data
    assert data["total"] == len(data["steps"])


def test_check_step_structure():
    result = _run("check")
    payload = json.loads(result.stdout)
    for step in payload["data"]["steps"]:
        assert "id" in step
        assert "label" in step
        assert "detail" in step
        assert "href" in step
        assert "done" in step


def test_check_known_step_ids():
    result = _run("check")
    payload = json.loads(result.stdout)
    ids = {s["id"] for s in payload["data"]["steps"]}
    expected = {"search_profile", "job_sources", "linkedin", "cv_library"}
    assert expected.issubset(ids), f"Missing steps: {expected - ids}"
