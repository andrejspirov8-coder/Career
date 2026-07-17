"""Argument parser for recruiter orchestration commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from career_job_search.integrations.linkedin.paths import (
    ACTION_PLAN_JSONL,
    DEFAULT_LINKEDIN_CONFIG,
    SESSION_STATE_JSON,
)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Recruiter scout/plan/dispatch orchestrator."
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_LINKEDIN_CONFIG,
        help="LinkedIn recruiter YAML config",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--headed",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Show automation browser (--no-headed = headless).",
    )
    shared.add_argument("--browser-channel", default=None)
    shared.add_argument(
        "--login-timeout-seconds",
        type=int,
        default=None,
        help="Maximum headed login wait before stopping cleanly.",
    )

    pf = sub.add_parser("preflight", help="Validate CV paths + show caps.")
    pf.add_argument(
        "--browse-status",
        action="store_true",
        help="Probe Chrome debugger / browse_ws port.",
    )

    scout = sub.add_parser("scout", parents=[shared])
    scout.add_argument("--variant", default=None)
    scout.add_argument(
        "--action-plan",
        type=Path,
        default=ACTION_PLAN_JSONL,
        help="Destination JSONL (default pipeline/recruiter_action_plan.jsonl)",
    )
    scout.add_argument(
        "--max-profiles",
        type=int,
        default=None,
        help="Cap profiles scored in this scout run.",
    )

    pl = sub.add_parser("plan", parents=[shared])
    pl.add_argument(
        "--tier",
        dest="tier_filter",
        default=None,
        help="Only queue rows tagged this tier from JSONL (e.g. tier_1). Omit for full queue.",
    )
    pl.add_argument(
        "--no-retries-first",
        action="store_true",
        help="Do not prepend skipped_no_connect retry URLs.",
    )
    pl.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Merge MCP discovery JSONL into action plan before planning (e.g. pipeline/mcp_discovery_batch.jsonl).",
    )

    dsp = sub.add_parser("dispatch", parents=[shared])
    dsp.add_argument("--dry-run", action="store_true")
    dsp.add_argument(
        "--allow-live-dispatch",
        action="store_true",
        help="Required for non-dry-run LinkedIn connection dispatch after manual review.",
    )
    dsp.add_argument("--tier", dest="tier_filter", default=None)
    dsp.add_argument("--max", dest="max_profiles", type=int, default=None)
    dsp.add_argument(
        "--session",
        type=Path,
        default=SESSION_STATE_JSON,
        help="Session JSON produced by plan (default recruiter_session_state.json)",
    )

    daily = sub.add_parser("daily", parents=[shared])
    daily.add_argument("--dry-run", action="store_true")
    daily.add_argument(
        "--allow-live-dispatch",
        action="store_true",
        help="Required when daily mode performs non-dry-run LinkedIn dispatch.",
    )
    daily.add_argument("--tier", dest="tier_filter_plan", default=None)
    daily.add_argument("--dispatch-tier", dest="tier_dispatch", default=None)
    daily.add_argument("--max-dispatch", type=int, default=None)
    daily.add_argument(
        "--max-scout",
        type=int,
        default=None,
        help="Cap profiles scored during the scout phase. Dry runs default to 5, or --max-dispatch when set.",
    )
    daily.add_argument("--variant", default=None)
    daily.add_argument(
        "--mode",
        choices=("tier", "hiring_network"),
        default="tier",
        help="tier = scout/plan/dispatch tiers; hiring_network = delegate to hiring_network_workflow daily.",
    )

    sub.add_parser("followup", parents=[shared])
    sub.add_parser("report")

    return ap
