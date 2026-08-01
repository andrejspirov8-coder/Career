#!/usr/bin/env python3
"""Generate TypeScript types from Python helper JSON Schemas."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HELPERS = [
    ("career_job_search.automation.control", "automation", "AutomationOverview"),
    ("career_job_search.opportunities.dashboard_adapter", "opportunities", "OpportunityOverview"),
    ("career_job_search.recruiters.dashboard_adapter", "recruiters", "RecruiterOverview"),
    ("career_job_search.cvs.catalogue_cli", "cvCatalogue", "CvCatalogue"),
    ("career_job_search.cvs.studio", "cvStudio", "CvStudioStatus"),
    ("career_job_search.cvs.drafting", "localDrafting", "LocalDraftingStatus"),
    ("career_job_search.notifications.center", "notifications", "NotificationOverview"),
    ("career_job_search.opportunities.preferences", "searchPreferences", "SearchPreferences"),
    ("career_job_search.workspace.control", "workspace", "WorkspaceControls"),
    ("career_job_search.automation.analytics", "analytics", "AnalyticsOverview"),
]

GENERATED_DIR = Path("dashboard/lib/generated")


def main() -> int:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

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
    for helper_module, helper_name, type_name in HELPERS:
        try:
            schema_json = subprocess.run(
                ["uv", "run", "python", "-m", helper_module, "--schema"],
                capture_output=True, text=True, check=True
            ).stdout
            schema = json.loads(schema_json)
            run_ts_gen(schema, GENERATED_DIR / f"{helper_name}-contracts.ts", type_name)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: {helper_module} --schema failed: {e.stderr}", file=sys.stderr)
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
        # Replace the interface declaration for the specific type only
        content = re.sub(
            rf"^export interface {re.escape(type_name)}\s*\{{",
            f"export type {type_name} = {{",
            content,
            flags=re.MULTILINE
        )
        # The original interface ends with a single "}" on its own line.
        # For "export type X = { ... }", we keep that single closing brace.
        # No extra replacement needed.
    out_path.write_text(content)
    print(f"Generated {out_path}")


if __name__ == "__main__":
    sys.exit(main())
