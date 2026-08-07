# Contract Generation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a compile-time contract sharing pipeline between Python helpers and TypeScript dashboard by generating TypeScript types from JSON Schema exported by Python helpers.

**Architecture:** Add `--schema` flag to all 11 Python helpers that outputs JSON Schema for their envelope + data shape. CI script runs schema export + `json-schema-to-typescript` to generate `dashboard/lib/generated/*.ts`. TypeScript imports generated types for compile-time validation.

**Tech Stack:** Python 3.11, uv, json-schema-to-typescript (npm), TypeScript 5.9, Next.js 16

## Global Constraints

- Python 3.11 only (pyproject.toml:25)
- Ruff line-length 88, target py311 (pyproject.toml:34-36)
- Dashboard: Node 22.22.2, Next.js 16.2.11, React 19.2.7
- All runtime data in `state/`, `runtime/`, `output/`, `packs/` (gitignored)
- Local agent sandbox denies network except localhost:11434
- Envelope schema: `career_python_helper_v1` (contracts.py:9)
- Helper scripts in `tools/` are thin wrappers; implementation in `src/career_job_search/`

---

### Task 1.1: Create Core Schema Module with Envelope + Helper Schemas

**Files:**
- Create: `src/career_job_search/core/schema.py`
- Test: `tests/test_schema_export.py`

**Interfaces:**
- Produces: `HELPER_ENVELOPE_SCHEMA` (dict), `AUTOMATION_OVERVIEW_SCHEMA`, `OPPORTUNITY_OVERVIEW_SCHEMA`, `RECRUITER_OVERVIEW_SCHEMA`, `CV_CATALOGUE_SCHEMA`, `CV_STUDIO_SCHEMA`, `DEV_AGENTS_OVERVIEW_SCHEMA`, `LOCAL_DRAFTING_SCHEMA`, `NOTIFICATIONS_OVERVIEW_SCHEMA`, `SEARCH_PREFERENCES_SCHEMA`, `WORKSPACE_CONTROLS_SCHEMA`, `ANALYTICS_OVERVIEW_SCHEMA` (all dict[str, Any])
- Consumes: None (foundational module)

- [ ] **Step 1: Write failing test for schema module existence**

```python
# tests/test_schema_export.py
from __future__ import annotations

import importlib.util
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_schema_export.py::test_schema_module_exists -v`
Expected: FAIL - ModuleNotFoundError / FileNotFoundError

- [ ] **Step 3: Implement schema.py with envelope + all helper schemas**

```python
# src/career_job_search/core/schema.py
"""JSON Schema definitions for Python helper contracts (envelope + data shapes)."""

from __future__ import annotations

from typing import Any


HELPER_ENVELOPE_SCHEMA: dict[str, Any] = {
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


AUTOMATION_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AutomationOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_automation_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "settings": {
            "type": "object",
            "required": ["schedule_enabled", "schedule_time", "timezone", "updated_at"],
            "properties": {
                "schedule_enabled": {"type": "boolean"},
                "schedule_time": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$"},
                "timezone": {"type": "string"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        },
        "worker": {
            "type": "object",
            "properties": {
                "online": {"type": "boolean"},
                "status": {"type": "string"},
                "mode": {"type": ["string", "null"]},
                "started_at": {"type": ["string", "null"], "format": "date-time"},
                "heartbeat_at": {"type": ["string", "null"], "format": "date-time"},
                "age_seconds": {"type": ["number", "null"]},
            },
        },
        "counts": {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        },
        "active_runs": {"type": "array"},
        "recent_runs": {"type": "array"},
        "source_health": {
            "type": "object",
            "properties": {
                "overall_status": {"type": "string", "enum": ["healthy", "stale", "attention", "failed", "not_run"]},
                "last_checked_at": {"type": ["string", "null"], "format": "date-time"},
                "age_hours": {"type": ["number", "null"]},
                "message": {"type": "string"},
                "sources": {"type": "array"},
            },
        },
        "available_actions": {"type": "array", "items": {"type": "string"}},
        "safety": {
            "type": "object",
            "properties": {
                "scheduled_linkedin_enabled": {"type": "boolean"},
                "live_linkedin_dispatch_enabled": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
    },
    "required": ["schema", "generated_at", "settings", "worker", "counts", "active_runs", "recent_runs", "source_health", "available_actions", "safety"],
}


OPPORTUNITY_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "OpportunityOverview",
    "type": "object",
    "properties": {
        "schema": {"type": "string", "enum": ["opportunity_dashboard_overview_v1", "opportunity_dashboard_overview_v2"]},
        "generated_at": {"type": "string", "format": "date-time"},
        "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
        "funnel": {"type": "object", "additionalProperties": {"type": "integer"}},
        "pipeline": {"type": "object", "additionalProperties": {"type": "integer"}},
        "queues": {"type": "object"},
        "safe_actions": {"type": "array", "items": {"type": "string"}},
        "search_profile": {
            "type": "object",
            "properties": {
                "daily_queue_size": {"type": "integer"},
                "updated_at": {"type": "string"},
            },
        },
        "helperError": {"type": ["string", "null"]},
    },
    "required": ["schema", "generated_at", "counts", "funnel", "pipeline", "queues", "safe_actions"],
}


RECRUITER_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "RecruiterOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "recruiter_dashboard_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "queue": {"type": "array"},
        "saved_views": {"type": "object"},
        "metrics": {"type": "object"},
        "live_dispatch": {"type": "object"},
        "operators": {"type": "array"},
    },
    "required": ["schema", "generated_at", "queue", "saved_views", "metrics", "live_dispatch", "operators"],
}


CV_CATALOGUE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CvCatalogue",
    "type": "object",
    "properties": {
        "schema": {"const": "cv_catalogue_v1"},
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug", "name", "language", "focus", "display_order", "source_filename", "pdf_stem", "target_titles", "keywords", "negative_keywords"],
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "language": {"type": "string"},
                    "focus": {"type": "string"},
                    "display_order": {"type": "integer"},
                    "source_filename": {"type": "string"},
                    "pdf_stem": {"type": "string"},
                    "target_titles": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "negative_keywords": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "required": ["schema", "variants"],
}


CV_STUDIO_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CvStudioStatus",
    "type": "object",
    "properties": {
        "schema": {"const": "career_cv_studio_status_v1"},
        "variant": {"type": "string"},
        "source": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "string"}},
        "unsaved_changes": {"type": "boolean"},
        "visual_pdf_exists": {"type": "boolean"},
        "ats_pdf_exists": {"type": "boolean"},
        "canva_text_exists": {"type": "boolean"},
        "history": {"type": "array"},
    },
    "required": ["schema", "variant", "source", "sections", "unsaved_changes", "visual_pdf_exists", "ats_pdf_exists", "canva_text_exists", "history"],
}


DEV_AGENTS_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "DevAgentOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_local_dev_agent_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "runs": {"type": "array"},
        "proposals": {"type": "array"},
        "rollout": {"type": "object"},
        "models": {"type": "object"},
        "autonomy": {"type": "object"},
    },
    "required": ["schema", "generated_at", "runs", "proposals", "rollout", "models", "autonomy"],
}


LOCAL_DRAFTING_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "LocalDraftingStatus",
    "type": "object",
    "properties": {
        "schema": {"const": "career_local_drafting_status_v1"},
        "enabled": {"type": "boolean"},
        "model": {"type": ["string", "null"]},
        "url": {"type": "string"},
    },
    "required": ["schema", "enabled", "model", "url"],
}


NOTIFICATIONS_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "NotificationOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_notification_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "items": {"type": "array"},
        "unread_count": {"type": "integer"},
        "settings": {"type": "object"},
    },
    "required": ["schema", "generated_at", "items", "unread_count", "settings"],
}


SEARCH_PREFERENCES_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SearchPreferences",
    "type": "object",
    "properties": {
        "schema": {"const": "career_search_preferences_v1"},
        "daily_queue_size": {"type": "integer", "minimum": 1, "maximum": 50},
        "work_arrangements": {"type": "array", "items": {"type": "string"}},
        "role_tracks": {"type": "array", "items": {"type": "string"}},
        "excluded_companies": {"type": "array", "items": {"type": "string"}},
        "excluded_keywords": {"type": "array", "items": {"type": "string"}},
        "min_fit_score": {"type": "number", "minimum": 0, "maximum": 100},
        "locations": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
        "updated_at": {"type": "string", "format": "date-time"},
    },
    "required": ["schema", "daily_queue_size", "work_arrangements", "role_tracks", "excluded_companies", "excluded_keywords", "min_fit_score", "locations", "sources", "updated_at"],
}


WORKSPACE_CONTROLS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "WorkspaceControls",
    "type": "object",
    "properties": {
        "schema": {"const": "career_workspace_controls_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "dashboard_runtime": {"type": "object"},
        "keychain": {"type": "object"},
        "startup": {"type": "object"},
        "backup": {"type": "object"},
    },
    "required": ["schema", "generated_at", "dashboard_runtime", "keychain", "startup", "backup"],
}


ANALYTICS_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AnalyticsOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_analytics_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "funnel": {"type": "object"},
        "data_quality": {"type": "object"},
        "by_source": {"type": "array"},
        "by_variant": {"type": "array"},
        "by_tailoring": {"type": "array"},
        "by_score": {"type": "array"},
        "outcome_history": {"type": "array"},
        "weekly_trend": {"type": "array"},
        "recruiters": {"type": "array"},
        "recommendations": {"type": "array"},
    },
    "required": ["schema", "generated_at", "funnel", "data_quality", "by_source", "by_variant", "by_tailoring", "by_score", "outcome_history", "weekly_trend", "recruiters", "recommendations"],
}


__all__ = [
    "HELPER_ENVELOPE_SCHEMA",
    "AUTOMATION_OVERVIEW_SCHEMA",
    "OPPORTUNITY_OVERVIEW_SCHEMA",
    "RECRUITER_OVERVIEW_SCHEMA",
    "CV_CATALOGUE_SCHEMA",
    "CV_STUDIO_SCHEMA",
    "DEV_AGENTS_OVERVIEW_SCHEMA",
    "LOCAL_DRAFTING_SCHEMA",
    "NOTIFICATIONS_OVERVIEW_SCHEMA",
    "SEARCH_PREFERENCES_SCHEMA",
    "WORKSPACE_CONTROLS_SCHEMA",
    "ANALYTICS_OVERVIEW_SCHEMA",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_schema_export.py::test_schema_module_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/career_job_search/core/schema.py tests/test_schema_export.py
git commit -m "feat: add core schema module with JSON Schema definitions for all helpers"
```

---

### Task 1.2: Add `--schema` Flag to All 11 Python Helper Scripts

**Files:**
- Modify: `tools/automation_control.py` (add `--schema` flag handling in `main()`)
- Modify: `tools/opportunity_dashboard.py` (add `--schema` flag)
- Modify: `tools/recruiter_dashboard.py` (add `--schema` flag)
- Modify: `tools/cv_catalogue.py` (add `--schema` flag)
- Modify: `tools/cv_studio.py` (add `--schema` flag)
- Modify: `tools/local_dev_agents.py` (add `--schema` flag)
- Modify: `tools/local_drafting.py` (add `--schema` flag)
- Modify: `tools/notification_center.py` (add `--schema` flag)
- Modify: `tools/search_preferences.py` (add `--schema` flag)
- Modify: `tools/workspace_control.py` (add `--schema` flag)
- Modify: `tools/career_analytics.py` (add `--schema` flag)
- Test: `tests/test_schema_export.py` (add tests for each helper)

**Interfaces:**
- Consumes: `src.career_job_search.core.schema` constants
- Produces: JSON Schema printed to stdout when `--schema` flag passed

- [ ] **Step 1: Write failing tests for each helper's `--schema` flag**

```python
# tests/test_schema_export.py (append)
import subprocess
import json

HELPER_SCHEMA_MAP = [
    ("automation_control", "AUTOMATION_OVERVIEW_SCHEMA"),
    ("opportunity_dashboard", "OPPORTUNITY_OVERVIEW_SCHEMA"),
    ("recruiter_dashboard", "RECRUITER_OVERVIEW_SCHEMA"),
    ("cv_catalogue", "CV_CATALOGUE_SCHEMA"),
    ("cv_studio", "CV_STUDIO_SCHEMA"),
    ("local_dev_agents", "DEV_AGENTS_OVERVIEW_SCHEMA"),
    ("local_drafting", "LOCAL_DRAFTING_SCHEMA"),
    ("notification_center", "NOTIFICATIONS_OVERVIEW_SCHEMA"),
    ("search_preferences", "SEARCH_PREFERENCES_SCHEMA"),
    ("workspace_control", "WORKSPACE_CONTROLS_SCHEMA"),
    ("career_analytics", "ANALYTICS_OVERVIEW_SCHEMA"),
]

def test_all_helpers_have_schema_flag():
    for helper, schema_name in HELPER_SCHEMA_MAP:
        result = subprocess.run(
            ["uv", "run", "python", f"tools/{helper}.py", "--schema"],
            capture_output=True, text=True, cwd="."
        )
        assert result.returncode == 0, f"{helper} --schema failed: {result.stderr}"
        schema = json.loads(result.stdout)
        assert schema.get("title") == schema_name, f"{helper} wrong schema title"
        assert "$schema" in schema
        print(f"✓ {helper} --schema OK")
```

- [ ] **Step 2: Run test to verify all fail**

Run: `uv run python -m pytest tests/test_schema_export.py::test_all_helpers_have_schema_flag -v`
Expected: FAIL - all 11 helpers return non-zero (flag not recognized)

- [ ] **Step 3: Implement `--schema` flag in automation_control.py**

```python
# tools/automation_control.py: modify build_parser() and main()

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career dashboard automation worker")
    parser.add_argument("--db", type=Path, default=DEFAULT_AUTOMATION_DB)
    parser.add_argument("--schema", action="store_true", help="Output JSON Schema and exit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    # ... existing subparsers ...
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.schema:
        from career_job_search.core.schema import AUTOMATION_OVERVIEW_SCHEMA
        import json
        print(json.dumps(AUTOMATION_OVERVIEW_SCHEMA, indent=2))
        return 0
    # ... existing command handling ...
```

- [ ] **Step 4: Repeat Step 3 for remaining 10 helpers** (each imports its schema constant and prints it)

```python
# tools/opportunity_dashboard.py
if args.schema:
    from career_job_search.core.schema import OPPORTUNITY_OVERVIEW_SCHEMA
    import json
    print(json.dumps(OPPORTUNITY_OVERVIEW_SCHEMA, indent=2))
    return 0

# tools/recruiter_dashboard.py
if args.schema:
    from career_job_search.core.schema import RECRUITER_OVERVIEW_SCHEMA
    import json
    print(json.dumps(RECRUITER_OVERVIEW_SCHEMA, indent=2))
    return 0

# tools/cv_catalogue.py
if args.schema:
    from career_job_search.core.schema import CV_CATALOGUE_SCHEMA
    import json
    print(json.dumps(CV_CATALOGUE_SCHEMA, indent=2))
    return 0

# tools/cv_studio.py
if args.schema:
    from career_job_search.core.schema import CV_STUDIO_SCHEMA
    import json
    print(json.dumps(CV_STUDIO_SCHEMA, indent=2))
    return 0

# tools/local_dev_agents.py
if args.schema:
    from career_job_search.core.schema import DEV_AGENTS_OVERVIEW_SCHEMA
    import json
    print(json.dumps(DEV_AGENTS_OVERVIEW_SCHEMA, indent=2))
    return 0

# tools/local_drafting.py
if args.schema:
    from career_job_search.core.schema import LOCAL_DRAFTING_SCHEMA
    import json
    print(json.dumps(LOCAL_DRAFTING_SCHEMA, indent=2))
    return 0

# tools/notification_center.py
if args.schema:
    from career_job_search.core.schema import NOTIFICATIONS_OVERVIEW_SCHEMA
    import json
    print(json.dumps(NOTIFICATIONS_OVERVIEW_SCHEMA, indent=2))
    return 0

# tools/search_preferences.py
if args.schema:
    from career_job_search.core.schema import SEARCH_PREFERENCES_SCHEMA
    import json
    print(json.dumps(SEARCH_PREFERENCES_SCHEMA, indent=2))
    return 0

# tools/workspace_control.py
if args.schema:
    from career_job_search.core.schema import WORKSPACE_CONTROLS_SCHEMA
    import json
    print(json.dumps(WORKSPACE_CONTROLS_SCHEMA, indent=2))
    return 0

# tools/career_analytics.py
if args.schema:
    from career_job_search.core.schema import ANALYTICS_OVERVIEW_SCHEMA
    import json
    print(json.dumps(ANALYTICS_OVERVIEW_SCHEMA, indent=2))
    return 0
```

- [ ] **Step 5: Run test to verify all pass**

Run: `uv run python -m pytest tests/test_schema_export.py::test_all_helpers_have_schema_flag -v`
Expected: PASS - all 11 helpers output valid JSON Schema

- [ ] **Step 6: Commit**

```bash
git add tools/automation_control.py tools/opportunity_dashboard.py tools/recruiter_dashboard.py tools/cv_catalogue.py tools/cv_studio.py tools/local_dev_agents.py tools/local_drafting.py tools/notification_center.py tools/search_preferences.py tools/workspace_control.py tools/career_analytics.py tests/test_schema_export.py
git commit -m "feat: add --schema flag to all 11 Python helpers for contract generation"
```

---

### Task 1.3: Create TypeScript Generation Script + Dashboard Config

**Files:**
- Create: `scripts/generate-contracts.py`
- Modify: `dashboard/package.json` (add `json-schema-to-typescript` dev dep)
- Modify: `dashboard/tsconfig.json` (add `lib/generated` to include)
- Modify: `dashboard/.gitignore` (add `lib/generated/`)
- Test: `tests/test_contract_generation.py`

**Interfaces:**
- Consumes: `--schema` output from all 11 helpers
- Produces: `dashboard/lib/generated/envelope.ts`, `dashboard/lib/generated/automation-contracts.ts`, etc.

- [ ] **Step 1: Write failing test for generation script**

```python
# tests/test_contract_generation.py
from __future__ import annotations

import subprocess
from pathlib import Path

def test_generate_typescript_types():
    result = subprocess.run(
        ["uv", "run", "python", "scripts/generate-contracts.py"],
        capture_output=True, text=True, cwd="."
    )
    assert result.returncode == 0, f"Generation failed: {result.stderr}"

    generated_dir = Path("dashboard/lib/generated")
    assert generated_dir.exists(), "Generated directory not created"

    # Verify envelope type generated
    envelope_file = generated_dir / "envelope.ts"
    assert envelope_file.exists(), "envelope.ts not generated"
    content = envelope_file.read_text()
    assert "PythonHelperEnvelopeV1" in content
    assert "career_python_helper_v1" in content

    # Verify at least one helper type generated
    automation_file = generated_dir / "automation-contracts.ts"
    assert automation_file.exists(), "automation-contracts.ts not generated"
    content = automation_file.read_text()
    assert "AutomationOverview" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_contract_generation.py::test_generate_typescript_types -v`
Expected: FAIL - script doesn't exist

- [ ] **Step 3: Implement generate-contracts.py**

```python
# scripts/generate-contracts.py
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
    out_path.write_text(content)
    print(f"Generated {out_path}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add dev dependency to dashboard**

Run: `cd dashboard && npm install --save-dev json-schema-to-typescript@15.0.0`

- [ ] **Step 5: Update tsconfig.json to include generated types**

```json
// dashboard/tsconfig.json:26-31
"include": [
  "next-env.d.ts",
  "**/*.ts",
  "**/*.tsx",
  ".next/types/**/*.ts",
  ".next/dev/types/**/*.ts",
  "lib/generated/**/*.ts"
],
```

- [ ] **Step 6: Update .gitignore**

```gitignore
# dashboard/.gitignore (add)
lib/generated/
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_contract_generation.py::test_generate_typescript_types -v`
Expected: PASS - all types generated

- [ ] **Step 8: Commit**

```bash
git add scripts/generate-contracts.py dashboard/package.json dashboard/package-lock.json dashboard/tsconfig.json dashboard/.gitignore dashboard/lib/generated/
git commit -m "feat: add TypeScript contract generation pipeline with json-schema-to-typescript"
```

---

### Task 1.4: Update TypeScript Bridge to Use Generated Envelope Type

**Files:**
- Modify: `dashboard/lib/server/python-bridge.ts` (import generated envelope, remove manual definition)
- Test: `tests/test_typescript_bridge.py` (verify TypeScript compiles)

**Interfaces:**
- Consumes: `dashboard/lib/generated/envelope.ts` exports `PythonHelperEnvelopeV1`
- Produces: `parsePythonHelperEnvelope` uses generated type

- [ ] **Step 1: Write failing test for TypeScript compilation**

```python
# tests/test_typescript_bridge.py
import subprocess

def test_dashboard_typescript_compiles_with_generated_types():
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        capture_output=True, text=True, cwd="dashboard"
    )
    assert result.returncode == 0, f"TypeScript compilation failed:\n{result.stdout}\n{result.stderr}"
```

- [ ] **Step 2: Run test to verify it fails (will fail after we modify python-bridge.ts but before we fix imports)**

Run: `uv run python -m pytest tests/test_typescript_bridge.py::test_dashboard_typescript_compiles_with_generated_types -v`
Expected: FAIL (will be fixed in next steps)

- [ ] **Step 3: Update python-bridge.ts to import generated envelope**

```typescript
// dashboard/lib/server/python-bridge.ts:27-32 (replace manual interface)
import type { PythonHelperEnvelopeV1 } from '@/lib/generated/envelope';

export type PythonHelperEnvelopeV1<T> = PythonHelperEnvelopeV1 & {
  data?: T;
};

// Remove the old manual definition (lines 27-32 in original)
```

- [ ] **Step 4: Run TypeScript typecheck to verify**

Run: `cd dashboard && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_typescript_bridge.py::test_dashboard_typescript_compiles_with_generated_types -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard/lib/server/python-bridge.ts tests/test_typescript_bridge.py
git commit -m "feat: update python-bridge to use generated envelope type"
```

---

### Task 1.5: Update Dashboard Helper Types to Use Generated Contracts

**Files:**
- Modify: `dashboard/lib/automation-data.ts` (import generated `AutomationOverview`)
- Modify: `dashboard/lib/opportunity-data.ts` (import generated `OpportunityOverview`)
- Modify: `dashboard/lib/recruiter-data.ts` (import generated `RecruiterOverview`)
- Modify: `dashboard/lib/cv-data.ts` (import generated `CvCatalogue`)
- Modify: `dashboard/lib/dev-agent-data.ts` (import generated `DevAgentOverview`)
- Modify: `dashboard/lib/local-drafting.ts` (import generated `LocalDraftingStatus`)
- Modify: `dashboard/lib/notification-data.ts` (import generated `NotificationOverview`)
- Modify: `dashboard/lib/search-preferences.ts` (import generated `SearchPreferences`)
- Modify: `dashboard/lib/workspace-control.ts` (import generated `WorkspaceControls`)
- Modify: `dashboard/lib/analytics-data.ts` (import generated `AnalyticsOverview`)
- Test: `tests/test_typescript_helpers.py` (verify all compile)

**Interfaces:**
- Each helper file consumes generated type for its data shape
- Produces: Type-safe `runPythonHelper<T>` calls

- [ ] **Step 1: Write failing test for all dashboard helpers compiling**

```python
# tests/test_typescript_helpers.py
import subprocess

def test_all_dashboard_helper_types_compile():
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        capture_output=True, text=True, cwd="dashboard"
    )
    assert result.returncode == 0, f"TypeScript compilation failed:\n{result.stdout}\n{result.stderr}"
```

- [ ] **Step 2: Update automation-data.ts**

```typescript
// dashboard/lib/automation-data.ts:7-103 (replace manual types with generated)
// KEEP: isAutomationKind, isAutomationRunId, isScheduleTime, runHelper, getAutomationOverview, getAutomationRun, startAutomationRun, cancelAutomationRun, retryAutomationRun, saveAutomationSchedule
// REPLACE: AutomationKind, AutomationStatus, DailySearchJob, AutomationRun, AutomationOverview with generated types

import type { AutomationOverview as GeneratedAutomationOverview } from '@/lib/generated/automation-contracts';

// Re-export with envelope
export type AutomationOverview = GeneratedAutomationOverview;

// Keep validation functions that operate on the data shape
export function isAutomationKind(value: unknown): value is 'daily_search' | 'cv_build' { ... }
export function isAutomationRunId(value: unknown): value is string { ... }
export function isScheduleTime(value: unknown): value is string { ... }
```

- [ ] **Step 3: Repeat for remaining 9 helper files** (each replaces manual type definitions with generated import)

- [ ] **Step 4: Run TypeScript typecheck**

Run: `cd dashboard && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Run test to verify**

Run: `uv run python -m pytest tests/test_typescript_helpers.py::test_all_dashboard_helper_types_compile -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard/lib/automation-data.ts dashboard/lib/opportunity-data.ts dashboard/lib/recruiter-data.ts dashboard/lib/cv-data.ts dashboard/lib/dev-agent-data.ts dashboard/lib/local-drafting.ts dashboard/lib/notification-data.ts dashboard/lib/search-preferences.ts dashboard/lib/workspace-control.ts dashboard/lib/analytics-data.ts tests/test_typescript_helpers.py
git commit -m "feat: update all dashboard helpers to use generated TypeScript contracts"
```

---

### Task 1.6: Add CI Integration for Contract Generation

**Files:**
- Modify: `.github/workflows/ci.yml` (add contract generation step to dashboard job)
- Test: N/A (verified by CI run)

**Interfaces:**
- Consumes: `scripts/generate-contracts.py`
- Produces: Generated types available for dashboard build/typecheck

- [ ] **Step 1: Add contract generation to CI**

```yaml
# .github/workflows/ci.yml:56-68 (dashboard job)
      - name: Generate TypeScript contracts
        working-directory: job-search
        run: |
          uv run python scripts/generate-contracts.py
      - name: Typecheck
        working-directory: job-search/dashboard
        run: npm run typecheck
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add TypeScript contract generation to dashboard CI pipeline"
```

---

### Task 1.7: Verify End-to-End Contract Pipeline

**Files:**
- Test: `tests/test_contract_pipeline_e2e.py`

**Interfaces:**
- Consumes: All previous tasks
- Produces: Confidence that pipeline works

- [ ] **Step 1: Write E2E test**

```python
# tests/test_contract_pipeline_e2e.py
import subprocess
import json

def test_contract_pipeline_e2e():
    """Verify: Python schema -> TS generation -> TypeScript compiles -> runtime works"""

    # 1. All helpers export schema
    for helper in ["automation_control", "opportunity_dashboard", "recruiter_dashboard", "cv_catalogue", "cv_studio", "local_dev_agents", "local_drafting", "notification_center", "search_preferences", "workspace_control", "career_analytics"]:
        result = subprocess.run(["uv", "run", "python", f"tools/{helper}.py", "--schema"], capture_output=True, text=True)
        assert result.returncode == 0
        schema = json.loads(result.stdout)
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"

    # 2. TypeScript generation succeeds
    result = subprocess.run(["uv", "run", "python", "scripts/generate-contracts.py"], capture_output=True, text=True)
    assert result.returncode == 0

    # 3. Dashboard typecheck passes
    result = subprocess.run(["npm", "run", "typecheck"], capture_output=True, text=True, cwd="dashboard")
    assert result.returncode == 0, f"TypeScript failed: {result.stderr}"

    # 4. Dashboard unit tests pass
    result = subprocess.run(["npm", "test"], capture_output=True, text=True, cwd="dashboard")
    assert result.returncode == 0, f"Dashboard tests failed: {result.stderr}"
```

- [ ] **Step 2: Run E2E test**

Run: `uv run python -m pytest tests/test_contract_pipeline_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_contract_pipeline_e2e.py
git commit -m "test: add end-to-end contract generation pipeline verification"
```

---

## Execution Order Summary

| Task | Description | Depends On |
|------|-------------|------------|
| 1.1 | Core schema module | — |
| 1.2 | `--schema` flag on all helpers | 1.1 |
| 1.3 | TS generation script + dashboard config | 1.2 |
| 1.4 | Update python-bridge.ts | 1.3 |
| 1.5 | Update all dashboard helper types | 1.3 |
| 1.6 | CI integration | 1.3 |
| 1.7 | E2E verification | 1.4, 1.5, 1.6 |

---

**Ready for subagent-driven execution.** Each task has explicit failing-test-first steps, implementation code, and verification commands.
