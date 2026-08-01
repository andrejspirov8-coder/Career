"""Integration test fixtures for Career job-search workspace."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

JOB_ROOT = Path(__file__).parent.parent.parent
DASHBOARD_PORT = 3999
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"


@pytest.fixture(scope="session")
def dashboard_server() -> str:
    """Start dashboard dev server on port 3999 for integration tests."""
    env = {
        **os.environ,
        "CAREER_DASHBOARD_TOKEN": "integration-test-token",
        "CAREER_DASHBOARD_PORT": str(DASHBOARD_PORT),
    }
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "career_job_search.workspace.dashboard_service", "--mode", "dev", "--port", str(DASHBOARD_PORT)],
        cwd=JOB_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server ready
    for _ in range(30):
        try:
            httpx.get(f"{DASHBOARD_URL}/login", timeout=1.0)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(f"Dashboard server failed to start: {stderr.decode()}")

    yield DASHBOARD_URL

    proc.terminate()
    proc.wait(timeout=10)


HELPER_MODULES = {
    "automation_control": "career_job_search.automation.control",
    "opportunity_dashboard": "career_job_search.opportunities.dashboard_adapter",
    "recruiter_dashboard": "career_job_search.recruiters.dashboard_adapter",
    "cv_catalogue": "career_job_search.cvs.catalogue_cli",
    "cv_studio": "career_job_search.cvs.studio",
    "local_drafting": "career_job_search.cvs.drafting",
    "notification_center": "career_job_search.notifications.center",
    "search_preferences": "career_job_search.opportunities.preferences",
    "workspace_control": "career_job_search.workspace.control",
    "career_analytics": "career_job_search.automation.analytics",
}


@pytest.fixture
def python_helper() -> Callable[[str, list[str]], dict]:
    """Call a Python helper via subprocess and return parsed JSON envelope."""

    def _call(helper: str, args: list[str]) -> dict:
        module = HELPER_MODULES.get(helper)
        if module is None:
            raise KeyError(f"Unknown helper: {helper}")
        result = subprocess.run(
            ["uv", "run", "python", "-m", module, *args],
            cwd=JOB_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        import json

        return json.loads(result.stdout) if result.stdout else {"ok": False, "error": result.stderr}

    return _call