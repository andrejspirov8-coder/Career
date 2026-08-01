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
    ("automation_control", "AutomationOverview"),
    ("opportunity_dashboard", "OpportunityOverview"),
    ("recruiter_dashboard", "RecruiterOverview"),
    ("cv_catalogue", "CvCatalogue"),
    ("cv_studio", "CvStudioStatus"),
    ("local_drafting", "LocalDraftingStatus"),
    ("notification_center", "NotificationOverview"),
    ("search_preferences", "SearchPreferences"),
    ("workspace_control", "WorkspaceControls"),
    ("career_analytics", "AnalyticsOverview"),
]


def test_all_helpers_have_schema_flag():
    for helper, schema_name in HELPER_SCHEMA_MAP:
        result = subprocess.run(
            ["uv", "run", "python", f"tools/{helper}.py", "--schema"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert result.returncode == 0, f"{helper} --schema failed: {result.stderr}"
        schema = json.loads(result.stdout)
        assert schema.get("title") == schema_name, f"{helper} wrong schema title"
        assert "$schema" in schema
        print(f"✓ {helper} --schema OK")