#!/usr/bin/env python3
"""Safe JSON helper for the local recruiter dashboard.

The dashboard may inspect queues, approve exact notes, edit queued notes, and
run dry-run workflow commands. It deliberately cannot trigger live LinkedIn
dispatch.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from career_job_search.core.contracts import helper_json
from career_job_search.core.time import utc_now_iso
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import (
    HIRING_NETWORK_ACTION_PLAN_JSONL,
    HIRING_NETWORK_RUN_STATE_JSON,
    JOB_ROOT,
    RECRUITERS_CSV,
)
from career_job_search.opportunities.repository import DEFAULT_OPPORTUNITY_DB
from career_job_search.recruiters.dashboard_actions import (
    SAFE_ACTIONS,
    SAFE_OPERATOR_ACTIONS,
    approve_dashboard_note,
    bulk_update_profile_status,
    mark_profile_review,
    mark_profile_skipped,
    record_dashboard_operator_action,
    run_dashboard_action,
    update_action_plan_note,
)
from career_job_search.recruiters.dashboard_storage import (
    ACTION_HISTORY_JSONL,
    RUNTIME_DIR,
    _active_run,
    _history_by_profile,
    _load_json,
    _profile_history_key,
    _recent_runs,
    read_jsonl_records,
    read_recruiter_rows,
)
from career_job_search.recruiters.dashboard_storage import (
    read_dashboard_action_history as read_dashboard_action_history,
)
from career_job_search.recruiters.dispatch_guard import validate_note_integrity
from career_job_search.recruiters.opportunity_targets import (
    opportunity_target_query_rows,
    opportunity_target_settings,
    safe_load_opportunity_targets,
)
from career_job_search.recruiters.policy import current_send_mode, risk_stop_state
from career_job_search.recruiters.repository import (
    DEFAULT_STATE_DB,
    approval_check,
    approval_metadata,
    latest_approval_metadata,
)
from career_job_search.recruiters.session_dashboard import (
    merge_session_queue_rows,
    resolve_session_state_path,
)

SCHEMA = "recruiter_dashboard_overview_v1"
PERSONA_STATS_JSON = JOB_ROOT / "pipeline" / "persona_stats.json"
MAX_NOTE_CHARS = 280


def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, indent=2))


def _risk_flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _approval_payload(row: dict[str, Any], db_path: Path) -> dict[str, Any]:
    profile_url = str(row.get("profile_url") or "")
    note = str(row.get("note") or "")
    check = approval_check(profile_url=profile_url, note=note, db_path=db_path)
    metadata = approval_metadata(profile_url=profile_url, note=note, db_path=db_path)
    payload = {
        "approved": check.approved,
        "reason": check.reason,
        "note_hash": check.note_hash,
        **metadata,
    }
    if not check.approved and check.reason == "missing_matching_approval":
        previous = latest_approval_metadata(profile_url=profile_url, db_path=db_path)
        if previous:
            payload["warning"] = "note_changed_after_approval"
            payload["previous_note_hash"] = previous.get("note_hash") or ""
    return payload


def _score_details(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank_score": row.get("rank_score") or row.get("primary_score"),
        "primary_score": row.get("primary_score"),
        "margin_over_second": row.get("margin_over_second"),
        "profile_confidence": row.get("profile_confidence")
        or row.get("persona_confidence"),
        "send_tier": str(row.get("send_tier") or ""),
        "decision": str(row.get("decision") or ""),
        "top_signals": row.get("top_signals") or [],
    }


def _profile_evidence(row: dict[str, Any]) -> dict[str, Any]:
    top_signals = row.get("top_signals") or []
    if not isinstance(top_signals, list):
        top_signals = [str(top_signals)]
    risk_flags = _risk_flags(row.get("risk_flags"))
    location = str(row.get("location") or "")
    company = str(row.get("company") or "")
    persona = str(row.get("persona") or "")
    cv_variant = str(row.get("cv_variant") or row.get("variant_slug") or "")
    source = str(row.get("source_backend") or row.get("source") or "action_plan")
    confidence = row.get("profile_confidence") or row.get("persona_confidence")
    return {
        "source": source,
        "company": {
            "name": company,
            "facts": [
                item for item in [company, str(row.get("headline") or "")] if item
            ],
        },
        "persona": {
            "label": persona,
            "evidence": [
                item
                for item in [persona, *[str(signal) for signal in top_signals]]
                if item
            ],
        },
        "cv_fit": {
            "variant": cv_variant,
            "score": row.get("primary_score") or row.get("rank_score"),
            "evidence": [str(signal) for signal in top_signals if str(signal).strip()],
        },
        "geo": {
            "location": location,
            "evidence": [location] if location else [],
        },
        "risk_flags": risk_flags,
        "confidence": confidence,
    }


def _score_explanation(row: dict[str, Any]) -> dict[str, str]:
    decision = str(row.get("decision") or "")
    tier = str(row.get("send_tier") or "")
    persona = str(row.get("persona") or "this profile")
    cv_variant = str(
        row.get("cv_variant") or row.get("variant_slug") or "the selected CV"
    )
    signals = row.get("top_signals") or []
    if not isinstance(signals, list):
        signals = [str(signals)]
    reason = ", ".join(str(signal) for signal in signals[:3] if str(signal).strip())
    if not reason:
        reason = "the available ranking fields"
    if decision == "skip" or tier == "skip":
        review_reason = "Skip because the score or risk flags are weak."
    elif decision == "approved" or tier == "auto_send":
        review_reason = "Ready for manual send after approval checks."
    else:
        review_reason = "Review before approval."
    return {
        "decision": decision,
        "send_tier": tier,
        "why_this_person": f"Matched {persona} using {reason}.",
        "why_this_cv": f"Best fit is {cv_variant}.",
        "why_review_or_skip": review_reason,
    }


def _note_quality(row: dict[str, Any]) -> dict[str, Any]:
    note = str(row.get("note") or "")
    issues: list[str] = []
    if not note.strip():
        issues.append("missing_note")
    if len(note) > MAX_NOTE_CHARS:
        issues.append("too_long")
    ok, reason = validate_note_integrity(note)
    if not ok:
        issues.append(reason)
    return {
        "valid": not issues,
        "length": len(note),
        "max_chars": MAX_NOTE_CHARS,
        "issues": issues,
    }


def _next_action(record: dict[str, Any]) -> str:
    if (
        record.get("status") == "sent"
        or record.get("score_details", {}).get("send_tier") == "sent"
    ):
        return "wait"
    if record.get("risk_flags"):
        return "review"
    if not record.get("note_quality", {}).get("valid"):
        return "edit_note"
    if record.get("approval", {}).get("approved"):
        return "copy_note"
    if record.get("decision") == "skip" or record.get("send_tier") == "skip":
        return "skip_profile"
    return "approve_note"


def _dashboard_record(
    row: dict[str, Any],
    db_path: Path,
    history_by_profile: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    profile_url = str(row.get("profile_url") or "")
    canon = lis.canonical_profile_url(profile_url) or profile_url
    record = {
        "profile_url": canon,
        "name": str(row.get("name") or ""),
        "headline": str(row.get("headline") or ""),
        "company": str(row.get("company") or ""),
        "location": str(row.get("location") or ""),
        "persona": str(row.get("persona") or ""),
        "cv_variant": str(row.get("cv_variant") or row.get("variant_slug") or ""),
        "rank_score": row.get("rank_score"),
        "send_tier": str(row.get("send_tier") or ""),
        "decision": str(row.get("decision") or ""),
        "risk_flags": _risk_flags(row.get("risk_flags")),
        "note": str(row.get("note") or ""),
        "note_reason": str(row.get("note_reason") or ""),
        "source_backend": str(row.get("source_backend") or ""),
        "target_company": str(row.get("target_company") or ""),
        "target_opportunity_id": str(row.get("target_opportunity_id") or ""),
        "target_role_title": str(row.get("target_role_title") or ""),
        "target_company_verified": bool(row.get("target_company_verified")),
        "approval": _approval_payload(row, db_path),
        "score_details": _score_details(row),
        "score_explanation": _score_explanation(row),
        "profile_evidence": _profile_evidence(row),
        "note_quality": _note_quality(row),
        "action_history": (history_by_profile or {}).get(canon, []),
    }
    record["next_action"] = _next_action(record)
    return record


def _queue_key(row: dict[str, Any]) -> str:
    send_tier = str(row.get("send_tier") or "")
    decision = str(row.get("decision") or "")
    if send_tier == "auto_send" and decision == "approved":
        return "auto_send"
    if send_tier == "queue_review" or decision == "review":
        return "review"
    if send_tier == "skip" or decision == "skip":
        return "skipped"
    return "review"


def _build_saved_views(
    queues: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    action_rows = [
        *queues["auto_send"],
        *queues["review"],
        *queues["skipped"],
    ]
    return {
        "needs_review": queues["review"],
        "auto_send_candidates": queues["auto_send"],
        "approved": [
            row for row in action_rows if row.get("approval", {}).get("approved")
        ],
        "skipped": queues["skipped"],
        "sent": queues["sent"],
        "risk_flags": [row for row in action_rows if row.get("risk_flags")],
    }


def _campaign_readiness(queues: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    action_rows = [
        *queues["auto_send"],
        *queues["review"],
        *queues["skipped"],
    ]
    ready_for_manual_send = [
        row
        for row in action_rows
        if row.get("approval", {}).get("approved")
        and row.get("note_quality", {}).get("valid")
        and not row.get("risk_flags")
    ]
    stale_notes = [
        row
        for row in action_rows
        if row.get("approval", {}).get("warning") == "note_changed_after_approval"
    ]
    risky_profiles = [row for row in action_rows if row.get("risk_flags")]
    approvals_valid = [
        row for row in action_rows if row.get("approval", {}).get("approved")
    ]
    return {
        "ready_for_manual_send": len(ready_for_manual_send),
        "approvals_valid": len(approvals_valid),
        "stale_notes": len(stale_notes),
        "risky_profiles": len(risky_profiles),
        "expected_manual_minutes": max(1, len(ready_for_manual_send) * 2)
        if ready_for_manual_send
        else 0,
    }


def build_metrics(
    action_rows: list[dict[str, Any]], recruiter_rows: list[dict[str, str]]
) -> dict[str, Any]:
    personas: dict[str, Counter[str]] = defaultdict(Counter)
    variants: dict[str, Counter[str]] = defaultdict(Counter)
    risk_flags: Counter[str] = Counter()

    for row in action_rows:
        persona = str(row.get("persona") or "(none)")
        variant = str(row.get("cv_variant") or row.get("variant_slug") or "(none)")
        personas[persona]["queued"] += 1
        variants[variant]["queued"] += 1
        for flag in _risk_flags(row.get("risk_flags")):
            risk_flags[flag] += 1

    for row in recruiter_rows:
        persona = (row.get("persona") or "(none)").strip() or "(none)"
        variant = (row.get("variant_slug") or "(none)").strip() or "(none)"
        status = (row.get("status") or "").strip()
        if status == "sent":
            personas[persona]["sent"] += 1
            variants[variant]["sent"] += 1
        if (row.get("accepted_at") or "").strip():
            personas[persona]["accepted"] += 1
            variants[variant]["accepted"] += 1
        if (row.get("reply_at") or "").strip():
            personas[persona]["reply"] += 1
            variants[variant]["reply"] += 1
        if (row.get("interview_at") or "").strip():
            personas[persona]["interview"] += 1
            variants[variant]["interview"] += 1

    def serialise(counter_map: dict[str, Counter[str]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, counts in sorted(counter_map.items()):
            sent = int(counts.get("sent", 0))
            accepted = int(counts.get("accepted", 0))
            reply = int(counts.get("reply", 0))
            out[key] = {
                "queued": int(counts.get("queued", 0)),
                "sent": sent,
                "accepted": accepted,
                "reply": reply,
                "interview": int(counts.get("interview", 0)),
                "accept_rate": accepted / sent if sent else 0.0,
                "reply_rate": reply / sent if sent else 0.0,
            }
        return out

    return {
        "personas": serialise(personas),
        "variants": serialise(variants),
        "risk_flags": dict(risk_flags.most_common()),
    }


def _opportunity_targets_overview(
    opportunity_db_path: Path | str,
) -> dict[str, Any]:
    settings = opportunity_target_settings({})
    targets, error = safe_load_opportunity_targets(
        db_path=opportunity_db_path,
        settings=settings,
    )
    query_rows = opportunity_target_query_rows(
        targets,
        queries_per_company=settings.queries_per_company,
    )
    return {
        "enabled": settings.enabled,
        "count": len(targets),
        "query_count": len(query_rows),
        "error": error,
        "companies": [
            {
                "company": target.company,
                "opportunity_id": target.opportunity_id,
                "title": target.title,
                "location": target.location,
                "cv_variant": target.cv_variant,
                "fit_score": target.fit_score,
                "live_status": target.live_status,
                "priority_reason": target.priority_reason,
            }
            for target in targets
        ],
    }


def build_overview(
    *,
    action_plan_path: Path = HIRING_NETWORK_ACTION_PLAN_JSONL,
    recruiters_csv_path: Path = RECRUITERS_CSV,
    state_db_path: Path = DEFAULT_STATE_DB,
    run_state_path: Path = HIRING_NETWORK_RUN_STATE_JSON,
    persona_stats_path: Path = PERSONA_STATS_JSON,
    runtime_dir: Path = RUNTIME_DIR,
    action_history_path: Path = ACTION_HISTORY_JSONL,
    session_state_path: Path | None = None,
    opportunity_db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    action_rows, malformed_rows = read_jsonl_records(action_plan_path)
    session_path = resolve_session_state_path(action_plan_path, session_state_path)
    merged_rows, session_queue_count = merge_session_queue_rows(
        action_rows, session_path
    )
    action_rows = merged_rows
    recruiter_rows = read_recruiter_rows(recruiters_csv_path)
    queues = {"auto_send": [], "review": [], "skipped": [], "sent": []}
    histories = _history_by_profile(action_history_path)

    approved_notes = 0
    for row in action_rows:
        record = _dashboard_record(row, state_db_path, histories)
        if record["approval"]["approved"]:
            approved_notes += 1
        queues[_queue_key(row)].append(record)

    sent_count = 0
    accepted_count = 0
    reply_count = 0
    interview_count = 0
    for row in recruiter_rows:
        status = (row.get("status") or "").strip()
        if status == "sent":
            sent_count += 1
        if (row.get("accepted_at") or "").strip():
            accepted_count += 1
        if (row.get("reply_at") or "").strip():
            reply_count += 1
        if (row.get("interview_at") or "").strip():
            interview_count += 1
        if status == "sent":
            profile_url = row.get("profile_url") or ""
            sent_note = row.get("final_note") or row.get("note_preview") or ""
            sent_record = {
                "profile_url": profile_url,
                "name": row.get("name") or "",
                "headline": row.get("headline") or "",
                "company": row.get("company") or "",
                "location": row.get("location") or "",
                "persona": row.get("persona") or "",
                "cv_variant": row.get("variant_slug") or "",
                "rank_score": row.get("rank_score") or "",
                "status": status,
                "send_tier": "sent",
                "decision": status,
                "risk_flags": [],
                "note": sent_note,
                "approval": {
                    "approved": False,
                    "reason": "sent_record",
                    "note_hash": "",
                },
                "score_details": {
                    "rank_score": row.get("rank_score") or "",
                    "send_tier": "sent",
                    "decision": status,
                },
                "score_explanation": {
                    "decision": status,
                    "send_tier": "sent",
                    "why_this_person": "Already recorded as sent.",
                    "why_this_cv": row.get("variant_slug") or "",
                    "why_review_or_skip": "Wait for a response or follow-up.",
                },
                "profile_evidence": _profile_evidence(
                    {
                        "profile_url": profile_url,
                        "name": row.get("name") or "",
                        "headline": row.get("headline") or "",
                        "company": row.get("company") or "",
                        "location": row.get("location") or "",
                        "persona": row.get("persona") or "",
                        "cv_variant": row.get("variant_slug") or "",
                        "source_backend": "recruiters_csv",
                    }
                ),
                "note_quality": _note_quality({"note": sent_note}),
                "next_action": "wait",
                "action_history": histories.get(_profile_history_key(profile_url), []),
            }
            queues["sent"].append(sent_record)

    saved_views = _build_saved_views(queues)
    queues["saved_views"] = saved_views
    run_history = _recent_runs(runtime_dir)
    send_mode = current_send_mode()
    readiness = _campaign_readiness(queues)
    run_state = _load_json(run_state_path) or {}
    risk_state = risk_stop_state(
        screen_state=str(
            run_state.get("screen_state") or run_state.get("risk_screen_state") or ""
        ),
        failure_rate=float(run_state.get("failure_rate") or 0.0),
        pending_invites=int(run_state.get("pending_invites") or 0),
        daily_cap_reached=bool(run_state.get("daily_cap_reached") or False),
    )

    return {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "send_mode": send_mode,
        "files": {
            "action_plan": str(action_plan_path),
            "recruiters_csv": str(recruiters_csv_path),
            "run_state": str(run_state_path),
            "state_db": str(state_db_path),
        },
        "counts": {
            "total_ranked": len(action_rows),
            "auto_send": len(queues["auto_send"]),
            "queue_review": len(queues["review"]),
            "skipped": len(queues["skipped"]),
            "approved_notes": approved_notes,
            "sent": sent_count,
            "accepted": accepted_count,
            "reply": reply_count,
            "interview": interview_count,
            "session_queue": session_queue_count,
            "malformed_action_rows": malformed_rows,
        },
        "queues": queues,
        "metrics": build_metrics(action_rows, recruiter_rows),
        "opportunity_targets": _opportunity_targets_overview(opportunity_db_path),
        "run_state": run_state,
        "persona_stats": _load_json(persona_stats_path) or {},
        "active_run": _active_run(runtime_dir),
        "recent_runs": run_history,
        "run_history": run_history,
        "campaign": {"readiness": readiness},
        "risk_stop_state": risk_state,
        "live_dispatch": {
            "mode": send_mode,
            "message": (
                "Manual send mode is active. Use Open Profile, Copy Note, and Mark Sent Manually."
                if send_mode == "manual"
                else "CLI-gated live dispatch is available only after exact approval checks."
            ),
            "auto_send_candidates": len(queues["auto_send"]),
            "approved_notes": approved_notes,
            "ready_for_cli_dispatch": send_mode == "cli_gated"
            and bool(queues["auto_send"])
            and approved_notes >= len(queues["auto_send"]),
            "ready_for_manual_send": readiness["ready_for_manual_send"],
        },
        "safe_actions": SAFE_ACTIONS,
    }


def _payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.cmd == "overview":
        return build_overview()
    if args.cmd == "action":
        return run_dashboard_action(args.name)
    if args.cmd == "approve":
        return approve_dashboard_note(profile_url=args.profile_url, note=args.note)
    if args.cmd == "update-note":
        return update_action_plan_note(profile_url=args.profile_url, note=args.note)
    if args.cmd == "mark-skipped":
        return mark_profile_skipped(profile_url=args.profile_url)
    if args.cmd == "mark-review":
        return mark_profile_review(profile_url=args.profile_url)
    if args.cmd == "bulk-mark-skipped":
        return bulk_update_profile_status(
            profile_urls=args.profile_url,
            target_status="skipped",
        )
    if args.cmd == "bulk-mark-review":
        return bulk_update_profile_status(
            profile_urls=args.profile_url,
            target_status="review",
        )
    if args.cmd == "operator-action":
        return record_dashboard_operator_action(
            action_type=args.action_type,
            profile_url=args.profile_url,
            note=args.note,
        )
    raise ValueError(f"Unsupported command: {args.cmd}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recruiter dashboard JSON helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("overview")

    action = sub.add_parser("action")
    action.add_argument("--name", required=True, choices=sorted(SAFE_ACTIONS))

    approve = sub.add_parser("approve")
    approve.add_argument("--profile-url", required=True)
    approve.add_argument("--note", required=True)

    update = sub.add_parser("update-note")
    update.add_argument("--profile-url", required=True)
    update.add_argument("--note", required=True)

    mark_skipped = sub.add_parser("mark-skipped")
    mark_skipped.add_argument("--profile-url", required=True)

    mark_review = sub.add_parser("mark-review")
    mark_review.add_argument("--profile-url", required=True)

    bulk_skipped = sub.add_parser("bulk-mark-skipped")
    bulk_skipped.add_argument("--profile-url", action="append", required=True)

    bulk_review = sub.add_parser("bulk-mark-review")
    bulk_review.add_argument("--profile-url", action="append", required=True)

    operator = sub.add_parser("operator-action")
    operator.add_argument(
        "--action-type", required=True, choices=sorted(SAFE_OPERATOR_ACTIONS)
    )
    operator.add_argument("--profile-url", required=True)
    operator.add_argument("--note", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _payload_from_args(args)
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": payload})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
