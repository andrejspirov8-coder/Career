"""Versioned command adapter for the private opportunity dashboard."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from career_job_search.core.contracts import helper_json
from career_job_search.opportunities.capture import capture_opportunity
from career_job_search.opportunities.dashboard_actions import (
    SAFE_OPPORTUNITY_ACTIONS,
    build_weekly_roi_summary,
    record_opportunity_action,
)
from career_job_search.opportunities.dashboard_common import opportunity_record
from career_job_search.opportunities.dashboard_overview import (
    build_opportunity_detail,
    build_opportunity_export,
    build_opportunity_overview,
)

__all__ = [
    "SAFE_OPPORTUNITY_ACTIONS",
    "build_opportunity_detail",
    "build_opportunity_export",
    "build_opportunity_overview",
    "build_weekly_roi_summary",
    "main",
    "opportunity_record",
    "record_opportunity_action",
]


def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, indent=2))


def _payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.cmd == "overview":
        return build_opportunity_overview()
    if args.cmd == "detail":
        return build_opportunity_detail(args.opportunity_id)
    if args.cmd == "export":
        return build_opportunity_export()
    if args.cmd == "weekly-roi":
        return build_weekly_roi_summary()
    if args.cmd == "capture":
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Capture payload must be a JSON object.")
        return capture_opportunity(payload)
    if args.cmd == "action":
        return record_opportunity_action(
            action_type=args.name,
            opportunity_id=args.opportunity_id,
            application_url=args.application_url,
            application_notes=args.application_notes,
            application_outcome=args.application_outcome,
            decision_reason=args.decision_reason,
            decision_note=args.decision_note,
        )
    raise ValueError(f"Unsupported command: {args.cmd}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Opportunity dashboard JSON helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("overview")
    detail = sub.add_parser("detail")
    detail.add_argument("--opportunity-id", required=True)
    sub.add_parser("export")
    sub.add_parser("weekly-roi")
    sub.add_parser("capture")
    action = sub.add_parser("action")
    action.add_argument("--name", required=True, choices=SAFE_OPPORTUNITY_ACTIONS)
    action.add_argument("--opportunity-id", required=True)
    action.add_argument("--application-url", default="")
    action.add_argument("--application-notes", default="")
    action.add_argument("--application-outcome", default="")
    action.add_argument("--decision-reason", default="")
    action.add_argument("--decision-note", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _payload_from_args(args)
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": payload})
    return 0
