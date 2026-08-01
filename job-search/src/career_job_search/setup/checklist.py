"""Check setup completeness for the Quick Start wizard."""

from __future__ import annotations

import argparse
from typing import Any

import yaml

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import project_path
from career_job_search.integrations.linkedin.paths import DEFAULT_LINKEDIN_CONFIG
from career_job_search.opportunities.preferences import load_search_preferences

DEFAULT_OPPORTUNITY_CONFIG = project_path("config", "opportunities.example.yaml")
USER_OPPORTUNITY_CONFIG = project_path("config", "opportunities.yaml")


def check_setup() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    # Step 1: Search preferences
    try:
        prefs = load_search_preferences()
        target_roles_filled = len(prefs.target_roles) > 0
    except Exception:
        target_roles_filled = False
    steps.append({
        "id": "search_profile",
        "label": "Define what you're looking for",
        "detail": "Target roles, locations, and salary preferences",
        "href": "/settings",
        "done": target_roles_filled,
    })

    # Step 2: Opportunity sources
    try:
        opp_path = USER_OPPORTUNITY_CONFIG if USER_OPPORTUNITY_CONFIG.exists() else DEFAULT_OPPORTUNITY_CONFIG
        if opp_path.exists():
            raw = yaml.safe_load(opp_path.read_text(encoding="utf-8")) or {}
            sources = (raw.get("opportunities") or {}).get("sources") or {}
            enabled = any(
                isinstance(src, dict) and src.get("enabled")
                for src in sources.values()
            )
        else:
            enabled = False
    except Exception:
        enabled = False
    steps.append({
        "id": "job_sources",
        "label": "Enable job sources",
        "detail": "Choose which platforms and career pages to search",
        "href": "/settings",
        "done": enabled,
    })

    # Step 3: LinkedIn config
    try:
        if DEFAULT_LINKEDIN_CONFIG.exists():
            raw = yaml.safe_load(DEFAULT_LINKEDIN_CONFIG.read_text(encoding="utf-8")) or {}
            has_browser = bool(raw.get("browser"))
        else:
            has_browser = False
    except Exception:
        has_browser = False
    steps.append({
        "id": "linkedin",
        "label": "Configure LinkedIn integration",
        "detail": "Browser, search, and automation settings for recruiter workflows",
        "href": "/settings",
        "done": has_browser,
    })

    # Step 4: CV library
    try:
        pdf_dir = project_path("cv", "pdf")
        pdfs = list(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
        cvs_ready = len(pdfs) >= 6
    except Exception:
        cvs_ready = False
    steps.append({
        "id": "cv_library",
        "label": "Build CV library",
        "detail": "Generate PDF versions for each CV variant",
        "href": "/cvs",
        "done": cvs_ready,
    })

    done_count = sum(1 for s in steps if s["done"])
    total = len(steps)
    return {
        "steps": steps,
        "done_count": done_count,
        "total": total,
        "complete": done_count == total,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check setup completeness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        data = check_setup()
    except Exception as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    print(helper_json({"ok": True, "data": data}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
