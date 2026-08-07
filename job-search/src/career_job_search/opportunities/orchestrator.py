#!/usr/bin/env python3
"""Safe local opportunity discovery and matching workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import project_path
from career_job_search.opportunities.alerts import (
    load_alert_payloads,
    opportunities_from_alert,
)
from career_job_search.opportunities.browser import (
    load_browser_job_payloads,
    opportunity_from_browser_job,
)
from career_job_search.opportunities.config_validation import (
    load_and_validate_config,
    suggest_source_fixes,
)
from career_job_search.opportunities.dashboard_adapter import (
    build_opportunity_overview,
)
from career_job_search.opportunities.error_classifier import (
    classify_all_results,
)
from career_job_search.opportunities.live import (
    DEFAULT_LIVE_CHECK_MAX_CANDIDATES,
    DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS,
    apply_daily_live_gate,
)
from career_job_search.opportunities.matching import match_opportunities
from career_job_search.opportunities.models import OpportunityStatus
from career_job_search.opportunities.preferences import (
    apply_search_preferences,
    load_search_preferences,
)
from career_job_search.opportunities.repository import (
    DEFAULT_OPPORTUNITY_DB,
    claim_deliveries,
    list_opportunities,
    mark_unseen_linkedin_browser_unverified,
    mark_unseen_opportunities_expired,
    record_source_run,
    save_daily_run,
    save_opportunity,
    undelivered_opportunities,
    upsert_opportunities,
)
from career_job_search.opportunities.sources import discover_opportunities_with_results

JOB_ROOT = project_path()
DEFAULT_CONFIG = project_path("config", "opportunities.example.yaml")


def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, indent=2))


def load_config(path: Path | None) -> dict[str, Any]:
    """Load and validate opportunity configuration.

    Falls back to sensible defaults when *path* is None, validates the
    YAML against Pydantic schemas when a file is supplied, and surfaces
    actionable fix suggestions on the first validation failure.
    """
    try:
        return load_and_validate_config(str(path) if path else None)
    except ValueError as exc:
        # If validation fails, try to add fix suggestions for operator guidance
        if path and path.exists():
            import yaml

            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if isinstance(raw, dict):
                    suggestions = suggest_source_fixes(raw)
                    if suggestions:
                        lines: list[str] = [f"{exc}"] + ["\n" + s for s in suggestions]
                        raise ValueError("\n".join(lines)) from exc
            except Exception:  # noqa: S110  # try each candidate config path; re-raise the last failure after the loop
                pass
        raise


def cmd_discover(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    batch = discover_opportunities_with_results(config)
    opportunities = batch.opportunities
    data = {
        "count": len(opportunities),
        "opportunities": [row.to_json_dict() for row in opportunities],
        "dry_run": bool(args.dry_run),
        "partial": batch.partial,
        "source_results": [row.to_dict() for row in batch.source_results],
        "source_issues": _source_issues(
            [row.to_dict() for row in batch.source_results]
        ),
    }
    if not args.dry_run:
        data["persisted"] = upsert_opportunities(opportunities, db_path=args.db)
        data["expired"] = mark_unseen_opportunities_expired(
            seen_dedupe_keys=[row.dedupe_key for row in opportunities],
            source_names=sorted(
                {
                    result.source
                    for result in batch.source_results
                    if result.snapshot_type == "snapshot"
                    and result.complete
                    and result.status in {"success", "empty"}
                }
            ),
            db_path=args.db,
        )
    json_response({"ok": True, "data": data})
    return 2 if batch.partial else 0


def cmd_match(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    scoring_config = (config.get("opportunities") or {}).get("scoring") or {}
    since = getattr(args, "since", None)
    if since:
        # Only re-match opportunities discovered or changed since the given date.
        # Skips records that are already matched/applied/skipped with no score
        # changes and haven't been modified since *since*.
        all_opps = list_opportunities(db_path=args.db)
        opportunities = [
            row
            for row in all_opps
            if (
                row.first_seen_at.startswith(since)
                or row.last_seen_at >= since
                or row.first_eligible_at.startswith(since)
                or row.live_checked_at.startswith(since)
                or row.match is None
                or row.match.score < 10
                or row.status
                in {
                    OpportunityStatus.NEW,
                    OpportunityStatus.MATCHED,
                    OpportunityStatus.REVIEW,
                }
            )
        ]
    else:
        opportunities = list_opportunities(db_path=args.db)
    matched = match_opportunities(opportunities, scoring_config=scoring_config)
    for row in matched:
        save_opportunity(row, db_path=args.db)
    persisted = len(matched)
    json_response(
        {
            "ok": True,
            "data": {
                "count": len(matched),
                "persisted": persisted,
                "opportunities": [row.to_json_dict() for row in matched],
            },
        }
    )
    return 0


def _short_row(row: dict[str, Any]) -> dict[str, Any]:
    match = row.get("match") or {}
    variant = str(match.get("best_variant") or "")
    output_dir = JOB_ROOT / "output"
    description = " ".join(str(row.get("description") or "").split())
    return {
        "opportunity_id": row.get("opportunity_id"),
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "remote_policy": row.get("remote_policy"),
        "location_eligibility": row.get("location_eligibility"),
        "salary_text": row.get("salary_text"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "listing_snippet": description[:320],
        "live_status": row.get("live_status"),
        "live_checked_at": row.get("live_checked_at"),
        "best_variant": variant,
        "recommended_cv_variant": variant,
        "recommended_cv_visual_pdf": (
            str(output_dir / f"andrej-spirov-cv-{variant}.pdf") if variant else ""
        ),
        "recommended_cv_ats_pdf": (
            str(output_dir / f"andrej-spirov-cv-{variant}-ats.pdf") if variant else ""
        ),
        "match_confidence": match.get("confidence"),
        "fit_score": match.get("fit_score") or match.get("score"),
        "next_action": row.get("next_action"),
    }


def _source_issues(source_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Turn source health metadata into concise operator-facing warnings.

    Uses the new error_classifier module for structured severity + action.
    """
    issues: list[dict[str, str]] = []
    # Gather alerts from the classifier for actionable reporting
    alerts = classify_all_results(source_results)
    alert_map = {a.source: a for a in alerts}

    for result in source_results:
        source = str(result.get("source") or "unknown")
        status = str(result.get("status") or "")

        alert = alert_map.get(source)
        if status == "failed":
            msg = str(result.get("error") or "source failed")
            if alert:
                msg = f"{alert.message} → {alert.action}"
            issues.append(
                {
                    "source": source,
                    "kind": "failed",
                    "message": msg,
                    "severity": alert.severity if alert else "medium",
                }
            )
        elif status == "monitor_only":
            issues.append(
                {
                    "source": source,
                    "kind": "monitor_only",
                    "message": (
                        "career-page watchlist only; no actual job postings were fetched"
                    ),
                }
            )
        elif result.get("complete") is False:
            issues.append(
                {
                    "source": source,
                    "kind": "coverage_limited",
                    "message": (
                        "source was capped, so unseen postings were not reconciled; "
                        f"{result.get('item_count', 0)} postings were imported"
                    ),
                }
            )
    return issues


def apply_daily_source_policy(
    config: dict[str, Any], *, exclude_linkedin: bool
) -> dict[str, Any]:
    """Apply the unattended dashboard's source boundary to a loaded config."""

    if not exclude_linkedin:
        return config
    opportunities_config = config.setdefault("opportunities", {})
    if not isinstance(opportunities_config, dict):
        raise ValueError("Opportunity config 'opportunities' must be a mapping.")
    sources = opportunities_config.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("Opportunity config 'sources' must be a mapping.")
    linkedin = sources.setdefault("linkedin", {})
    if not isinstance(linkedin, dict):
        raise ValueError("Opportunity config LinkedIn source must be a mapping.")
    linkedin["enabled"] = False
    return config


def cmd_import_alerts(args: argparse.Namespace) -> int:
    if not args.stdin:
        raise ValueError("import-alerts requires --stdin")
    payloads = load_alert_payloads(sys.stdin)
    opportunities = []
    errors: list[str] = []
    source_counts: dict[str, int] = {}
    for payload in payloads:
        result = opportunities_from_alert(payload)
        opportunities.extend(result.opportunities)
        errors.extend(result.errors)
        for row in result.opportunities:
            source_counts[row.source] = source_counts.get(row.source, 0) + 1

    persisted = upsert_opportunities(opportunities, db_path=args.db)
    run_id = f"alerts_{uuid4().hex}"
    source_results: list[dict[str, Any]] = []
    for source, count in sorted(source_counts.items()):
        source_results.append(
            record_source_run(
                source=source,
                status="success",
                snapshot_type="incremental",
                item_count=count,
                duration_ms=0,
                error="",
                run_id=run_id,
                db_path=args.db,
            )
        )
    if not source_results and errors:
        source_results.append(
            record_source_run(
                source="job_alerts",
                status="failed",
                snapshot_type="incremental",
                item_count=0,
                duration_ms=0,
                error="; ".join(errors),
                run_id=run_id,
                db_path=args.db,
            )
        )

    partial = bool(errors)
    json_response(
        {
            "ok": True,
            "data": {
                "run_id": run_id,
                "messages_processed": len(payloads),
                "imported": len(opportunities),
                "persisted": persisted,
                "partial": partial,
                "errors": errors,
                "source_results": source_results,
            },
        }
    )
    return 2 if partial else 0


def cmd_import_browser(args: argparse.Namespace) -> int:
    if not args.stdin:
        raise ValueError("import-browser requires --stdin")
    payloads = load_browser_job_payloads(sys.stdin)
    opportunities = []
    errors: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        try:
            opportunities.append(opportunity_from_browser_job(payload))
        except ValueError as exc:
            errors.append(f"job {index}: {exc}")

    persisted = upsert_opportunities(opportunities, db_path=args.db)
    reconciled_unseen = mark_unseen_linkedin_browser_unverified(
        seen_native_source_ids=[
            row.native_source_id for row in opportunities if row.native_source_id
        ],
        snapshot_complete=bool(args.reconcile and not errors),
        db_path=args.db,
    )
    run_id = f"browser_{uuid4().hex}"
    source_result = record_source_run(
        source="linkedin:browser",
        status="success" if opportunities else ("failed" if errors else "empty"),
        snapshot_type="snapshot" if args.reconcile else "incremental",
        item_count=len(opportunities),
        duration_ms=0,
        error="; ".join(errors),
        run_id=run_id,
        db_path=args.db,
    )
    partial = bool(errors)
    json_response(
        {
            "ok": True,
            "data": {
                "run_id": run_id,
                "jobs_processed": len(payloads),
                "imported": len(opportunities),
                "persisted": persisted,
                "reconciled_unseen": reconciled_unseen,
                "partial": partial,
                "errors": errors,
                "source_results": [source_result],
                "source_issues": _source_issues([source_result]),
            },
        }
    )
    return 2 if partial else 0


def cmd_report(args: argparse.Namespace) -> int:
    overview = build_opportunity_overview(db_path=args.db)
    if args.summary:
        saved_views = overview["queues"]["saved_views"]
        summaries_by_id = {
            str(row.get("opportunity_id") or ""): row
            for row in overview["queues"]["all"]
        }

        def rows_for(view: str, limit: int) -> list[dict[str, Any]]:
            return [
                summaries_by_id[opportunity_id]
                for opportunity_id in saved_views.get(view, [])[:limit]
                if opportunity_id in summaries_by_id
            ]

        json_response(
            {
                "ok": True,
                "data": {
                    "counts": overview["counts"],
                    "fresh_live_matches": [
                        _short_row(row) for row in rows_for("fresh_live_matches", 10)
                    ],
                    "top_5_today": [
                        _short_row(row) for row in rows_for("top_5_today", 5)
                    ],
                    "review_queue": {
                        "fresh_live_matches": len(
                            saved_views.get("fresh_live_matches", [])
                        ),
                        "top_5_today": len(saved_views.get("top_5_today", [])),
                        "apply_today": len(saved_views.get("apply_today", [])),
                        "needs_cv_tailoring": len(
                            saved_views.get("needs_cv_tailoring", [])
                        ),
                        "needs_live_verification": len(
                            saved_views.get("needs_live_verification", [])
                        ),
                        "missing_outcome": len(saved_views.get("missing_outcome", [])),
                        "follow_up": len(saved_views.get("follow_up", [])),
                        "risk_flags": len(saved_views.get("risk_flags", [])),
                    },
                },
            }
        )
        return 0
    json_response({"ok": True, "data": overview})
    return 0


def cmd_daily_queue(args: argparse.Namespace) -> int:
    run_id = f"daily_{uuid4().hex}"
    search_preferences = load_search_preferences()
    config = apply_daily_source_policy(
        apply_search_preferences(load_config(args.config), search_preferences),
        exclude_linkedin=bool(args.exclude_linkedin),
    )
    batch = discover_opportunities_with_results(config)
    opportunities = batch.opportunities
    source_results = [row.to_dict() for row in batch.source_results]
    source_issues = _source_issues(source_results)
    for result in batch.source_results:
        record_source_run(
            source=result.source,
            status=result.status,
            snapshot_type=result.snapshot_type,
            item_count=result.item_count,
            duration_ms=result.duration_ms,
            error=result.error,
            run_id=run_id,
            db_path=args.db,
        )

    seen_dedupe_keys = [row.dedupe_key for row in opportunities]
    persisted_discovered = upsert_opportunities(opportunities, db_path=args.db)
    complete_snapshot_sources = sorted(
        {
            result.source
            for result in batch.source_results
            if result.snapshot_type == "snapshot"
            and result.complete
            and result.status in {"success", "empty"}
        }
    )
    expired = mark_unseen_opportunities_expired(
        seen_dedupe_keys=seen_dedupe_keys,
        source_names=complete_snapshot_sources,
        db_path=args.db,
    )

    scoring_config = (config.get("opportunities") or {}).get("scoring") or {}
    matched = match_opportunities(
        list_opportunities(db_path=args.db),
        scoring_config=scoring_config,
    )
    for row in matched:
        save_opportunity(row, db_path=args.db)
    persisted_matched = len(matched)
    live_config = (config.get("opportunities") or {}).get("liveness") or {}
    live_rows = list_opportunities(db_path=args.db)
    live_before = {
        row.opportunity_id: (
            row.live_status,
            row.live_checked_at,
            row.live_check_method,
            row.live_check_note,
            row.status,
            row.likely_closed,
            tuple(row.evidence.risk_flags),
        )
        for row in live_rows
    }
    live_checked_rows = apply_daily_live_gate(
        live_rows,
        fresh_dedupe_keys=seen_dedupe_keys,
        max_page_checks=int(
            live_config.get("max_page_checks") or DEFAULT_LIVE_CHECK_MAX_CANDIDATES
        ),
        timeout=int(
            live_config.get("network_timeout_seconds")
            or DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS
        ),
    )
    changed_live_rows = 0
    for row in live_checked_rows:
        after = (
            row.live_status,
            row.live_checked_at,
            row.live_check_method,
            row.live_check_note,
            row.status,
            row.likely_closed,
            tuple(row.evidence.risk_flags),
        )
        if live_before.get(row.opportunity_id) != after:
            changed_live_rows += 1
            save_opportunity(row, db_path=args.db)
    overview = build_opportunity_overview(
        db_path=args.db,
        search_preferences=search_preferences,
    )
    saved_views = overview["queues"]["saved_views"]
    candidate_rows = saved_views.get(
        "delivery_candidates",
        saved_views.get("fresh_live_matches", []),
    )
    candidates_by_id = {
        row.opportunity_id: row
        for row in list_opportunities(db_path=args.db)
        if row.opportunity_id in set(candidate_rows)
    }
    ordered_candidates = [
        candidates_by_id[opportunity_id]
        for opportunity_id in candidate_rows
        if opportunity_id in candidates_by_id
    ]
    ordered_candidates = undelivered_opportunities(
        ordered_candidates,
        db_path=args.db,
    )
    delivery_candidate_count = len(ordered_candidates)
    delivered = claim_deliveries(
        ordered_candidates[: search_preferences.daily_queue_size],
        run_id,
        preview=bool(args.preview),
        db_path=args.db,
    )
    delivered_rows = [_short_row(row.to_json_dict()) for row in delivered]

    data = {
        "run_id": run_id,
        "partial": batch.partial,
        "preview": bool(args.preview),
        "discovered": len(opportunities),
        "persisted_discovered": persisted_discovered,
        "matched": len(matched),
        "persisted_matched": persisted_matched,
        "expired": expired,
        "live_checked": changed_live_rows,
        "counts": overview["counts"],
        "source_results": source_results,
        "source_issues": source_issues,
        "delivery_log": str(args.db),
        "delivery_candidate_count": delivery_candidate_count,
        "shown_count": len(delivered_rows),
        "omitted_count": max(0, delivery_candidate_count - len(delivered_rows)),
        "new_live_jobs": delivered_rows,
        "fresh_live_matches": delivered_rows,
        "review_queue": {
            "fresh_live_matches": len(delivered_rows),
            "top_5_today": len(saved_views.get("top_5_today", [])),
            "apply_today": len(saved_views.get("apply_today", [])),
            "needs_cv_tailoring": len(saved_views.get("needs_cv_tailoring", [])),
            "needs_live_verification": len(
                saved_views.get("needs_live_verification", [])
            ),
            "missing_outcome": len(saved_views.get("missing_outcome", [])),
            "follow_up": len(saved_views.get("follow_up", [])),
            "risk_flags": len(saved_views.get("risk_flags", [])),
        },
    }
    if not args.preview:
        save_daily_run(
            run_id,
            "partial" if batch.partial else "complete",
            batch.partial,
            data,
            db_path=args.db,
        )
    json_response(
        {
            "ok": True,
            "data": data,
        }
    )
    return 2 if batch.partial else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Opportunity intelligence workflow")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--db", type=Path, default=DEFAULT_OPPORTUNITY_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)

    discover = sub.add_parser("discover")
    discover.add_argument("--dry-run", action="store_true")

    alert_import = sub.add_parser("import-alerts")
    alert_import.add_argument("--stdin", action="store_true")

    browser_import = sub.add_parser("import-browser")
    browser_import.add_argument("--stdin", action="store_true")
    browser_import.add_argument(
        "--reconcile",
        action="store_true",
        help="treat the input as a complete LinkedIn browser snapshot",
    )

    match_cmd = sub.add_parser("match")
    match_cmd.add_argument(
        "--since",
        type=str,
        default=None,
        help="Only re-match opportunities discovered or changed since YYYY-MM-DD",
    )
    report = sub.add_parser("report")
    report.add_argument("--summary", action="store_true")
    daily = sub.add_parser("daily-queue")
    daily.add_argument("--preview", action="store_true")
    daily.add_argument(
        "--exclude-linkedin",
        action="store_true",
        help=(
            "disable LinkedIn browser discovery for this run; used by the "
            "unattended local dashboard scheduler"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "discover":
            return cmd_discover(args)
        if args.cmd == "import-alerts":
            return cmd_import_alerts(args)
        if args.cmd == "import-browser":
            return cmd_import_browser(args)
        if args.cmd == "match":
            return cmd_match(args)
        if args.cmd == "report":
            return cmd_report(args)
        if args.cmd == "daily-queue":
            return cmd_daily_queue(args)
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    raise SystemExit(f"Unsupported command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
