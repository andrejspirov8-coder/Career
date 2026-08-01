#!/usr/bin/env python3
"""
Automated Career Workspace Workflow Orchestrator

Full pipeline: Scout → Plan → Dispatch → Analytics

Usage:
  python3 -m career_job_search.automation.legacy_workflow              # Full cycle
  python3 -m career_job_search.automation.legacy_workflow scout        # Scout only
  python3 -m career_job_search.automation.legacy_workflow plan         # Plan only
  python3 -m career_job_search.automation.legacy_workflow dispatch     # Dispatch only
  python3 -m career_job_search.automation.legacy_workflow analytics    # Analytics only
"""

import subprocess
from datetime import datetime

from career_job_search.core.paths import PROJECT_ROOT


class CareerWorkflow:
    """Orchestrate Career workspace automation pipeline"""

    def __init__(self):
        self.base_dir = PROJECT_ROOT
        self.pipeline_dir = self.base_dir / "pipeline"
        self.start_time = datetime.now()
        self.pipeline_dir.mkdir(exist_ok=True)

    def log(self, message, level="INFO"):
        """Print timestamped log message"""
        prefix = {
            "INFO": "ℹ️",
            "OK": "✅",
            "WAIT": "⏳",
            "ERROR": "❌",
            "HEADER": "📍"
        }.get(level, "➜")
        print(f"{prefix} {message}")

    def run_command(self, cmd, description):
        """Execute shell command with error handling"""
        print()
        self.log(description, "HEADER")
        print("─" * 70)

        full_cmd = f"cd {self.base_dir} && {cmd}"
        result = subprocess.run(full_cmd, shell=True, cwd=str(self.base_dir))  # noqa: S602

        if result.returncode == 0:
            self.log(f"{description} - Complete", "OK")
        else:
            self.log(f"{description} - Failed", "ERROR")
            raise RuntimeError(f"{description} failed")

    def scout_phase(self):
        """Phase 1: Scout & Score"""
        self.log("SCOUT: Discovering & Scoring Profiles", "HEADER")
        cmd = "uv run python3 -m career_job_search.recruiters.orchestrator scout --headed"
        self.run_command(cmd, "Scout")
