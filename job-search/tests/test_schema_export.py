from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def test_schema_module_exists():
    spec = importlib.util.spec_from_file_location(
        "schema", Path("src/career_job_search/core/schema.py")
    )
    assert spec is not None, "schema.py must exist"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "HELPER_ENVELOPE_SCHEMA")
    assert module.HELPER_ENVELOPE_SCHEMA["properties"]["schema"]["const"] == "career_python_helper_v1"


HELPER_SCHEMA_MAP = [
    ("career_job_search.automation.control", "AutomationOverview"),
    ("career_job_search.opportunities.dashboard_adapter", "OpportunityOverview"),
    ("career_job_search.recruiters.dashboard_adapter", "RecruiterOverview"),
    ("career_job_search.cvs.catalogue_cli", "CvCatalogue"),
    ("career_job_search.cvs.studio", "CvStudioStatus"),
    ("career_job_search.cvs.drafting", "LocalDraftingStatus"),
    ("career_job_search.notifications.center", "NotificationOverview"),
    ("career_job_search.opportunities.preferences", "SearchPreferences"),
    ("career_job_search.workspace.control", "WorkspaceControls"),
    ("career_job_search.automation.analytics", "AnalyticsOverview"),
]


def test_all_helpers_have_schema_flag():
    for helper, schema_name in HELPER_SCHEMA_MAP:
        result = subprocess.run(
            ["uv", "run", "python", "-m", helper, "--schema"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert result.returncode == 0, f"{helper} --schema failed: {result.stderr}"
        schema = json.loads(result.stdout)
        assert schema.get("title") == schema_name, f"{helper} wrong schema title"
        assert "$schema" in schema
        print(f"✓ {helper} --schema OK")