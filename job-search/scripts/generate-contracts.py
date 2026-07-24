#!/usr/bin/env python3
"""Generate TypeScript types from Python helper JSON Schemas."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HELPERS = [
    ("automation_control", "automation", "AutomationOverview"),
    ("opportunity_dashboard", "opportunities", "OpportunityOverview"),
    ("recruiter_dashboard", "recruiters", "RecruiterOverview"),
    ("cv_catalogue", "cvCatalogue", "CvCatalogue"),
    ("cv_studio", "cvStudio", "CvStudioStatus"),
    ("local_dev_agents", "developmentAgents", "DevAgentOverview"),
    ("local_drafting", "localDrafting", "LocalDraftingStatus"),
    ("notification_center", "notifications", "NotificationOverview"),
    ("search_preferences", "searchPreferences", "SearchPreferences"),
    ("workspace_control", "workspace", "WorkspaceControls"),
    ("career_analytics", "analytics", "AnalyticsOverview"),
]

GENERATED_DIR = Path("dashboard/lib/generated")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    # Generate envelope type first
    envelope_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "PythonHelperEnvelopeV1",
        "type": "object",
        "properties": {
            "schema": {"const": "career_python_helper_v1"},
            "ok": {"type": "boolean"},
            "data": {"type": "object"},
            "error": {"type": "string"},
        },
        "required": ["schema"],
    }
    run_ts_gen(envelope_schema, GENERATED_DIR / "envelope.ts", "PythonHelperEnvelopeV1")

    # Generate per-helper types
    for helper_script, helper_name, type_name in HELPERS:
        try:
            schema_json = subprocess.run(
                ["uv", "run", "python", f"tools/{helper_script}.py", "--schema"],
                capture_output=True, text=True, check=True
            ).stdout
            schema = json.loads(schema_json)
            run_ts_gen(schema, GENERATED_DIR / f"{helper_name}-contracts.ts", type_name)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: {helper_script} --schema failed: {e.stderr}", file=sys.stderr)
            return 1

    return 0


def run_ts_gen(schema: dict, out_path: Path, type_name: str) -> None:
    result = subprocess.run(
        ["npx", "json-schema-to-typescript", "--style.singleQuotes", "true", "--declareExternallyReferenced", "true"],
        input=json.dumps(schema),
        capture_output=True, text=True, check=True
    )
    # Fix: json-schema-to-typescript outputs `export interface` but we want `export type` for envelope
    content = result.stdout
    if type_name == "PythonHelperEnvelopeV1":
        content = content.replace("export interface ", "export type ")
        content = content.replace(f"export type {type_name} {{", f"export type {type_name} = {{")
    out_path.write_text(content)
    print(f"Generated {out_path}")


if __name__ == "__main__":
    sys.exit(main())