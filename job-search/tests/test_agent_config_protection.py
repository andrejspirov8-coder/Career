# tests/test_agent_config_protection.py
from __future__ import annotations

import yaml


def test_scan_paths_includes_core_layers():
    with open("config/local_dev_agents.yaml") as f:
        config = yaml.safe_load(f)
    scan_paths = config.get("planner", {}).get("scan_paths", [])
    required = [
        "src/career_job_search/core",
        "src/career_job_search/domain",
        "src/career_job_search/application",
        "src/career_job_search/infrastructure",
        "cv",
    ]
    for path in required:
        assert path in scan_paths, f"{path} must be in scan_paths"


def test_write_forbidden_includes_core_layers():
    from career_job_search.dev_agents.common import WRITE_FORBIDDEN_PATHS

    required = [
        "src/career_job_search/core",
        "src/career_job_search/domain",
        "src/career_job_search/application",
        "src/career_job_search/infrastructure",
        "cv/build_cv_pdf.py",
        "cv/variant_profiles.yaml",
    ]
    for path in required:
        assert any(path in p for p in WRITE_FORBIDDEN_PATHS), f"{path} must be write-forbidden"