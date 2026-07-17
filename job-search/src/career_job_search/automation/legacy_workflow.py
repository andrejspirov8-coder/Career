#!/usr/bin/env python3
"""
Automated Career Workspace Workflow Orchestrator

Full pipeline: Scout → Plan → Dispatch → Analytics

Usage:
  python3 tools/automated_workflow.py              # Full cycle
  python3 tools/automated_workflow.py scout        # Scout only
  python3 tools/automated_workflow.py plan         # Plan only
  python3 tools/automated_workflow.py dispatch     # Dispatch only
  python3 tools/automated_workflow.py analytics    # Analytics only
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
        result = subprocess.run(full_cmd, shell=True, cwd=str(self.base_dir))

        if result.returncode == 0:
            self.log(f"{description} - Complete", "OK")
        else:
            self.log(f"{description} - Failed", "ERROR")
            raise RuntimeError(f"{description} failed")

    def scout_phase(self):
        """Phase 1: Scout & Score"""
        self.log("SCOUT: Discovering & Scoring Profiles", "HEADER")
        cmd = "uv run python3 tools/recruiter_orchestrate.py scout --headed"
        self.run_command(cmd, "Scout")
