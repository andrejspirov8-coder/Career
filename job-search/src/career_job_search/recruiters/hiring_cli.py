"""Argument parser for the hiring-network compatibility command."""

from __future__ import annotations

import argparse
from pathlib import Path

from career_job_search.integrations.linkedin.paths import (
    ACTION_PLAN_JSONL,
    CANDIDATES_DISCOVERY_CSV,
    CANDIDATES_VALIDATED_CSV,
    DEFAULT_LINKEDIN_CONFIG,
    HIRING_NETWORK_ACTION_PLAN_JSONL,
)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Agentic LinkedIn hiring-network workflow")
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument(
        "--source-action-plan",
        type=Path,
        default=Path("pipeline/recruiter_action_plan.jsonl"),
        help="Scout input from career_job_search.recruiters.orchestrator",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=HIRING_NETWORK_ACTION_PLAN_JSONL,
        help="Ranked hiring-network JSONL output",
    )
    ap.add_argument("--browser-channel", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight")

    rank = sub.add_parser("rank", help="Rank an existing scout action plan")
    _ = rank

    daily = sub.add_parser("daily", help="Scout, rank, and optionally auto-send")
    daily.add_argument("--headed", default=True, action=argparse.BooleanOptionalAction)
    daily.add_argument("--dry-run", action="store_true")
    daily.add_argument("--auto-send", action="store_true")
    daily.add_argument("--max", type=int, default=None)
    daily.add_argument(
        "--allow-live-dispatch",
        action="store_true",
        help="Required when --auto-send performs non-dry-run LinkedIn dispatch.",
    )
    daily.add_argument("--skip-scout", action="store_true")
    daily.add_argument("--variant", default=None)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument(
        "--headed", default=True, action=argparse.BooleanOptionalAction
    )
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.add_argument(
        "--allow-live-dispatch",
        action="store_true",
        help="Required for non-dry-run LinkedIn connection dispatch after manual review.",
    )
    dispatch.add_argument("--tier", default="auto_send")
    dispatch.add_argument("--max", type=int, default=None)
    dispatch.add_argument(
        "--only-new",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip profiles already in recruiters.csv (default: on for --full-auto)",
    )

    report = sub.add_parser("report")
    report.add_argument("--persona-stats", action="store_true")

    bridge = sub.add_parser(
        "bridge",
        help="Convert validated CSV to scout JSONL for rank/dispatch",
    )
    bridge.add_argument("--validated-csv", type=Path, default=CANDIDATES_VALIDATED_CSV)
    bridge.add_argument("--action-plan", type=Path, default=ACTION_PLAN_JSONL)
    bridge.add_argument("--approved-only", action="store_true")
    bridge.add_argument("--write-action-plan", action="store_true")
    bridge.add_argument("--dry-run", action="store_true")

    graph = sub.add_parser("graph", help="LangGraph three-agent pipeline")
    graph_sub = graph.add_subparsers(dest="graph_cmd", required=True)
    graph_run = graph_sub.add_parser("run", help="Run graph pipeline stage")
    graph_run.add_argument(
        "--stage",
        default="all",
        choices=("all", "discovery", "validate", "rank", "dispatch"),
    )
    graph_run.add_argument(
        "--dry-run", default=True, action=argparse.BooleanOptionalAction
    )
    graph_run.add_argument("--no-llm", action="store_true")
    graph_run.add_argument(
        "--verbose-llm",
        action="store_true",
        help="Log each Ollama agent call to stderr + pipeline/llm_trace.jsonl",
    )
    graph_run.add_argument(
        "--full-auto",
        action="store_true",
        help="CLI-gated live send path; blocked in manual mode and also requires --allow-live-dispatch.",
    )
    graph_run.add_argument(
        "--allow-live-dispatch",
        action="store_true",
        help="Required with --full-auto for non-dry-run LinkedIn dispatch when LINKEDIN_SEND_MODE=cli_gated.",
    )
    graph_run.add_argument(
        "--headed", default=True, action=argparse.BooleanOptionalAction
    )
    graph_run.add_argument("--auto-approve-review", action="store_true")
    graph_run.add_argument("--max", type=int, default=None)
    graph_run.add_argument(
        "--backend",
        default="auto",
        choices=("auto", "exa", "firecrawl", "offline"),
    )
    graph_run.add_argument(
        "--discovery-csv", type=Path, default=CANDIDATES_DISCOVERY_CSV
    )
    graph_run.add_argument(
        "--validated-csv", type=Path, default=CANDIDATES_VALIDATED_CSV
    )
    graph_run.add_argument("--action-plan", type=Path, default=ACTION_PLAN_JSONL)
    graph_run.add_argument(
        "--output", type=Path, default=HIRING_NETWORK_ACTION_PLAN_JSONL
    )
    graph_run.add_argument("--no-cache", action="store_true")
    graph_run.add_argument(
        "--no-merge-mcp",
        action="store_true",
        help="Skip merging stale mcp_discovery_batch.jsonl rows into discovery CSV",
    )
    graph_run.add_argument(
        "--only-new",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip profiles already in recruiters.csv (default: on for --full-auto)",
    )
    graph_run.add_argument(
        "--fresh-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Clear action-plan JSONL before run (default: on for --full-auto)",
    )
    graph_run.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip profile enrichment before rank",
    )
    graph_run.add_argument(
        "--enrich-browser",
        action="store_true",
        help="Use Playwright to scrape LinkedIn profiles (requires login)",
    )

    return ap
