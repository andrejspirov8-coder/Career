"""Dashboard adapter for local opportunity review."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from matching_lib import JOB_ROOT, load_profiles
from opportunity_models import (
    Opportunity,
    OpportunityPack,
    OpportunityStatus,
    next_action_for_opportunity,
    utc_now_iso,
)
from opportunity_state import (
    DEFAULT_OPPORTUNITY_DB,
    actions_for_opportunity,
    get_opportunity,
    latest_daily_run,
    list_opportunities,
    record_action,
    save_opportunity,
)
from pack_lib import write_pack_files

PACKS_DIR = JOB_ROOT / "packs"
APPLICATIONS_CSV = JOB_ROOT / "pipeline" / "applications.csv"
RECRUITERS_CSV = JOB_ROOT / "pipeline" / "recruiters.csv"
APPLICATION_COLUMNS = [
    "date_iso",
    "company",
    "title",
    "variant_slug",
    "source",
    "outcome",
    "deadline_date",
    "match_score",
    "match_confidence",
    "salary_range",
    "tailored_cv",
    "response_date",
    "opportunity_id",
    "pack_dir",
    "application_url",
    "notes",
]
SUBMITTED_OUTCOMES = {"applied", "screening", "interview", "offer", "rejected"}
POSITIVE_OUTCOMES = {"interview", "offer"}

SAFE_OPPORTUNITY_ACTIONS = [
    "mark_review",
    "mark_skipped",
    "mark_apply_ready",
    "generate_pack",
    "mark_applied",
    "log_application",
    "snooze_followup",
]

BEST_MATCH_BLOCKING_FLAGS = {
    "duplicate",
    "likely_closed",
    "low_cv_score",
    "needs_live_verification",
    "possible_scam",
    "vague_role",
    "watchlist_only",
    "weak_location_fit",
    "location_ineligible",
    "remote_eligibility_unverified",
}


def opportunity_record(
    opportunity: Opportunity,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    data = opportunity.to_json_dict()
    data["action_history"] = actions_for_opportunity(
        opportunity.opportunity_id,
        db_path=db_path,
    )
    return data


def _date_from_iso(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def _is_europe_fit(row: dict[str, Any]) -> bool:
    eligibility = str(row.get("location_eligibility") or "")
    if eligibility:
        return eligibility in {
            "eligible_vilnius",
            "eligible_lt_remote",
            "eligible_eu_remote",
        }
    text = " ".join(
        str(row.get(key) or "")
        for key in ("location", "remote_policy", "description", "title")
    ).lower()
    return any(
        token in text
        for token in (
            "vilnius",
            "lithuania",
            "lietuva",
            "baltic",
            "remote eu",
            "remote europe",
            "europe",
            "emea",
            "uk",
            "germany",
            "netherlands",
            "nordic",
        )
    )


def _risk_flags(row: dict[str, Any]) -> list[str]:
    return list((row.get("evidence") or {}).get("risk_flags") or [])


def _is_clean_best_match(row: dict[str, Any]) -> bool:
    flags = set(_risk_flags(row))
    return not flags.intersection(BEST_MATCH_BLOCKING_FLAGS)


def _has_fresh_live_evidence(row: dict[str, Any]) -> bool:
    checked = _date_from_iso(str(row.get("live_checked_at") or ""))
    if row.get("live_status") != "live" or checked != datetime.now().date():
        return False
    if row.get("source") == "linkedin" and row.get("source_kind") == "job_board":
        evidence_facts = set((row.get("evidence") or {}).get("source_facts") or [])
        return (
            "chrome:linkedin_job_detail" in evidence_facts
            and str(row.get("live_check_method") or "") == "linkedin_browser"
        )
    return True


def _is_best_match(row: dict[str, Any]) -> bool:
    return (
        (row.get("match") or {}).get("score", 0) >= 14
        and row.get("status") in {"matched", "apply_ready"}
        and _is_clean_best_match(row)
        and _has_fresh_live_evidence(row)
    )


def _match_score(row: dict[str, Any]) -> float:
    match = row.get("match") or {}
    for key in ("fit_score", "score"):
        try:
            return float(match.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0.0


def _has_confident_cv_match(row: dict[str, Any]) -> bool:
    match = row.get("match") or {}
    try:
        cv_score = float(match.get("cv_score") or 0.0)
        margin = float(match.get("margin_over_second") or 0.0)
    except (TypeError, ValueError):
        return False
    return (
        str(match.get("confidence") or "") == "clear_winner"
        and cv_score >= 10.0
        and margin >= 5.0
    )


def _is_top_today_candidate(row: dict[str, Any]) -> bool:
    if row.get("status") not in {"matched", "apply_ready"}:
        return False
    if (
        not _is_europe_fit(row)
        or not _is_clean_best_match(row)
        or not _has_fresh_live_evidence(row)
        or not _has_confident_cv_match(row)
    ):
        return False
    score = _match_score(row)
    if row.get("next_action") == "tailor_cv":
        return score >= 12
    return score >= 14


def _is_new_today(row: dict[str, Any], today: date) -> bool:
    first_seen = _date_from_iso(
        str(row.get("first_seen_at") or row.get("discovered_at") or "")
    )
    return first_seen == today


def _is_fresh_live_match(row: dict[str, Any], today: date) -> bool:
    return _is_new_today(row, today) and _is_top_today_candidate(row)


def _is_delivery_candidate(row: dict[str, Any]) -> bool:
    # Delivery is separate from the dashboard's "new today" view. A role is
    # new to the daily output when it is live and absent from the delivery
    # ledger, even if the workspace first saw it on an earlier day. The ledger
    # filter is applied atomically immediately before delivery is claimed.
    return bool(str(row.get("source_url") or "").strip()) and _is_top_today_candidate(
        row
    )


def _top_today_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
    action_priority = {
        "make_pack": 3,
        "apply_manual": 3,
        "tailor_cv": 2,
        "review": 1,
    }.get(str(row.get("next_action") or ""), 0)
    return (_match_score(row), action_priority, str(row.get("company") or ""))


def _needs_live_verification(row: dict[str, Any]) -> bool:
    if row.get("source_kind") not in {
        "manual_inbox",
        "job_alert",
        "job_board",
        "web_search",
    }:
        return False
    if row.get("status") in {"applied", "skipped", "expired", "follow_up"}:
        return False
    if row.get("live_status") == "live":
        return False
    flags = set(_risk_flags(row))
    if flags.intersection(
        {"duplicate", "likely_closed", "possible_scam", "watchlist_only"}
    ):
        return False
    return _is_europe_fit(row) and _match_score(row) >= 8


def _saved_views(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    today = datetime.now().date()
    closing_cutoff = today + timedelta(days=14)
    views = {
        "new_today": [
            row
            for row in rows
            if _date_from_iso(
                str(row.get("first_seen_at") or row.get("discovered_at") or "")
            )
            == today
        ],
        "updated_roles": [row for row in rows if row.get("source_updated_at")],
        "closing_soon": [
            row
            for row in rows
            if (deadline := _date_from_iso(str(row.get("deadline") or "")))
            and today <= deadline <= closing_cutoff
            and row.get("status") not in {"applied", "skipped", "expired"}
        ],
        "apply_today": [
            row
            for row in rows
            if row.get("status") == "apply_ready"
            and row.get("next_action") in {"make_pack", "apply_manual"}
            and _is_europe_fit(row)
            and _is_clean_best_match(row)
            and _has_fresh_live_evidence(row)
        ],
        "best_europe_matches": [
            row for row in rows if _is_best_match(row) and _is_europe_fit(row)
        ],
        "best_matches": [row for row in rows if _is_best_match(row)],
        "needs_review": [row for row in rows if row.get("status") == "review"],
        "apply_ready": [row for row in rows if row.get("status") == "apply_ready"],
        "needs_cv_tailoring": [
            row for row in rows if row.get("next_action") == "tailor_cv"
        ],
        "needs_live_verification": [
            row for row in rows if _needs_live_verification(row)
        ],
        "fresh_live_matches": sorted(
            [row for row in rows if _is_fresh_live_match(row, today)],
            key=_top_today_sort_key,
            reverse=True,
        ),
        "delivery_candidates": _prioritize_delivery_candidates(
            [row for row in rows if _is_delivery_candidate(row)]
        ),
        "company_watchlist": [
            row for row in rows if row.get("source_kind") == "company_site"
        ],
        "recruiter_contact": [
            row for row in rows if row.get("next_action") == "contact_recruiter"
        ],
        "applied": [row for row in rows if row.get("status") == "applied"],
        "missing_outcome": [row for row in rows if row.get("status") == "applied"],
        "follow_up": [row for row in rows if row.get("status") == "follow_up"],
        "skipped": [row for row in rows if row.get("status") == "skipped"],
        "expired": [row for row in rows if row.get("status") == "expired"],
        "likely_duplicate": [row for row in rows if "duplicate" in _risk_flags(row)],
        "likely_expired": [
            row
            for row in rows
            if row.get("likely_closed") or row.get("status") == "expired"
        ],
        "risk_flags": [row for row in rows if _risk_flags(row)],
    }
    top_candidates: dict[str, dict[str, Any]] = {}
    for row in (
        *views["apply_today"],
        *views["best_europe_matches"],
        *views["needs_cv_tailoring"],
    ):
        if _is_top_today_candidate(row):
            top_candidates[str(row["opportunity_id"])] = row
    views["top_5_today"] = sorted(
        top_candidates.values(),
        key=_top_today_sort_key,
        reverse=True,
    )[:5]
    return views


def _prioritize_delivery_candidates(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=_top_today_sort_key, reverse=True)
    local = [
        row for row in ranked if row.get("location_eligibility") == "eligible_vilnius"
    ]
    remote = [
        row
        for row in ranked
        if row.get("location_eligibility")
        in {"eligible_lt_remote", "eligible_eu_remote"}
    ]
    featured: list[dict[str, Any]] = []
    company_counts: dict[str, int] = {}
    for pool, limit in ((local, 6), (remote, 4)):
        for row in pool:
            company = str(row.get("company") or "").casefold()
            if company_counts.get(company, 0) >= 2:
                continue
            featured.append(row)
            company_counts[company] = company_counts.get(company, 0) + 1
            if sum(candidate in pool for candidate in featured) >= limit:
                break
    featured_ids = {str(row.get("opportunity_id") or "") for row in featured}
    return [
        *featured,
        *[
            row
            for row in ranked
            if str(row.get("opportunity_id") or "") not in featured_ids
        ],
    ]


def build_opportunity_overview(
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    opportunities = list_opportunities(db_path=db_path)
    rows = [opportunity_record(row, db_path=db_path) for row in opportunities]
    saved_views = _saved_views(rows)
    latest_run = latest_daily_run(db_path=db_path)
    if latest_run:
        delivered_ids = [
            str(item.get("opportunity_id") or "")
            for item in (latest_run.get("output") or {}).get("new_live_jobs", [])
        ]
        rows_by_id = {str(row.get("opportunity_id") or ""): row for row in rows}
        saved_views["fresh_live_matches"] = [
            rows_by_id[opportunity_id]
            for opportunity_id in delivered_ids
            if opportunity_id in rows_by_id
        ]
    return {
        "schema": "opportunity_dashboard_overview_v1",
        "generated_at": utc_now_iso(),
        "counts": {
            "total": len(rows),
            "new_today": len(saved_views["new_today"]),
            "fresh_live_matches": len(saved_views["fresh_live_matches"]),
            "updated_roles": len(saved_views["updated_roles"]),
            "closing_soon": len(saved_views["closing_soon"]),
            "top_5_today": len(saved_views["top_5_today"]),
            "apply_today": len(saved_views["apply_today"]),
            "needs_live_verification": len(saved_views["needs_live_verification"]),
            "best_europe_matches": len(saved_views["best_europe_matches"]),
            "best_matches": len(saved_views["best_matches"]),
            "needs_review": len(saved_views["needs_review"]),
            "apply_ready": len(saved_views["apply_ready"]),
            "applied": len(saved_views["applied"]),
            "missing_outcome": len(saved_views["missing_outcome"]),
            "follow_up": len(saved_views["follow_up"]),
            "skipped": len(saved_views["skipped"]),
            "likely_duplicate": len(saved_views["likely_duplicate"]),
            "likely_expired": len(saved_views["likely_expired"]),
            "risk_flags": len(saved_views["risk_flags"]),
        },
        "queues": {
            "all": rows,
            "saved_views": saved_views,
        },
        "safe_actions": SAFE_OPPORTUNITY_ACTIONS,
    }


def build_opportunity_detail(
    opportunity_id: str,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> dict[str, Any]:
    opportunity = get_opportunity(opportunity_id, db_path=db_path)
    if opportunity is None:
        raise ValueError(f"Opportunity not found: {opportunity_id}")
    return opportunity_record(opportunity, db_path=db_path)


def _pack_result(opportunity: Opportunity) -> dict[str, Any]:
    if not opportunity.match:
        raise ValueError("Opportunity must be matched before generating a pack.")
    return {
        "job": {
            "title": opportunity.title,
            "company": opportunity.company,
            "url": opportunity.source_url,
            "source": opportunity.source,
            "job_id": opportunity.opportunity_id,
            "body": opportunity.description,
            "job_file": None,
        },
        "recommendation": {
            "variant_slug": opportunity.match.best_variant,
            "confidence": opportunity.match.confidence,
            "primary_score": opportunity.match.score,
            "tie_break_score": 0,
            "margin_over_second": opportunity.match.margin_over_second,
        },
        "runner_up": {
            "variant_slug": opportunity.match.runner_up_variant,
            "primary_score": opportunity.match.runner_up_score,
        },
        "variants_ranked": [],
    }


def _generate_pack(
    opportunity: Opportunity,
    *,
    packs_dir: Path = PACKS_DIR,
) -> dict[str, Any]:
    variants = load_profiles()
    pack_id = opportunity.opportunity_id
    pack_dir = packs_dir / pack_id
    generated = True
    if pack_dir.exists():
        files = {
            "readme": str(pack_dir / "README.txt"),
            "match_json": str(pack_dir / "MATCH.json"),
            "keyword_gaps": str(pack_dir / "KEYWORD_GAPS.md"),
            "job_input": str(pack_dir / "job_input.txt"),
        }
        generated = False
    else:
        files = write_pack_files(
            _pack_result(opportunity),
            pack_id,
            pack_dir,
            variants,
            overwrite=False,
        )
    opportunity.pack = OpportunityPack(
        pack_id=pack_id,
        pack_dir=str(pack_dir),
        files=files,
        generated_at=utc_now_iso(),
    )
    return {
        "generated": generated,
        "pack_id": pack_id,
        "pack_dir": str(pack_dir),
        "files": files,
    }


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _application_row(
    opportunity: Opportunity,
    *,
    application_url: str = "",
) -> dict[str, str]:
    match = opportunity.match
    pack_dir = opportunity.pack.pack_dir if opportunity.pack else ""
    return {
        "date_iso": date.today().isoformat(),
        "company": opportunity.company,
        "title": opportunity.title,
        "variant_slug": match.best_variant if match else "",
        "source": opportunity.source,
        "outcome": "applied",
        "deadline_date": opportunity.deadline,
        "match_score": _format_number(match.score if match else None),
        "match_confidence": match.confidence if match else "",
        "salary_range": opportunity.salary_text,
        "tailored_cv": "yes" if pack_dir else "no",
        "response_date": "",
        "opportunity_id": opportunity.opportunity_id,
        "pack_dir": pack_dir,
        "application_url": application_url or opportunity.source_url,
        "notes": "Logged from opportunity queue; actual application submitted manually.",
    }


def _append_application_log(
    opportunity: Opportunity,
    *,
    applications_csv: Path = APPLICATIONS_CSV,
    application_url: str = "",
) -> dict[str, Any]:
    path = Path(applications_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = _application_row(opportunity, application_url=application_url)
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=APPLICATION_COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    return {
        "application_logged": True,
        "application_csv": str(path),
        **row,
    }


def _source_stats(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        source = (row.get("source") or "unknown").strip() or "unknown"
        outcome = (row.get("outcome") or "").strip().lower()
        bucket = buckets.setdefault(source, {"submitted": 0, "interviews": 0})
        if outcome in SUBMITTED_OUTCOMES:
            bucket["submitted"] += 1
        if outcome in POSITIVE_OUTCOMES:
            bucket["interviews"] += 1
    out: list[dict[str, Any]] = []
    for source, counts in buckets.items():
        submitted = counts["submitted"]
        interviews = counts["interviews"]
        out.append(
            {
                "source": source,
                "submitted": submitted,
                "interviews": interviews,
                "interview_rate": interviews / submitted if submitted else 0.0,
            }
        )
    return out


def build_weekly_roi_summary(
    *,
    applications_csv: Path = APPLICATIONS_CSV,
    recruiters_csv: Path = RECRUITERS_CSV,
) -> dict[str, Any]:
    applications = _csv_rows(Path(applications_csv))
    recruiters = _csv_rows(Path(recruiters_csv))

    submitted = 0
    interviews = 0
    missing_outcome = 0
    for row in applications:
        outcome = (row.get("outcome") or "").strip().lower()
        if outcome in SUBMITTED_OUTCOMES:
            submitted += 1
        if outcome in POSITIVE_OUTCOMES:
            interviews += 1
        if outcome in {"", "applied"}:
            missing_outcome += 1

    source_stats = _source_stats(applications)
    best_sources = sorted(
        source_stats,
        key=lambda row: (row["interview_rate"], row["submitted"], row["source"]),
        reverse=True,
    )
    worst_sources = sorted(
        source_stats,
        key=lambda row: (row["interview_rate"], -row["submitted"], row["source"]),
    )

    recruiter_sent = [
        row
        for row in recruiters
        if (row.get("status") or "").strip().lower() in {"sent", "pending", "accepted"}
    ]
    missing_accepted_at = sum(
        1 for row in recruiter_sent if not (row.get("accepted_at") or "").strip()
    )
    missing_reply_at = sum(
        1 for row in recruiter_sent if not (row.get("reply_at") or "").strip()
    )
    missing_interview_at = sum(
        1 for row in recruiter_sent if not (row.get("interview_at") or "").strip()
    )

    if missing_outcome:
        next_action = "Update missing application outcomes first."
    elif missing_accepted_at or missing_reply_at or missing_interview_at:
        next_action = "Log recruiter accept, reply, and interview outcomes next."
    elif submitted == 0:
        next_action = "Log one manual application from Top 5 Today."
    else:
        next_action = "Review Top 5 Today and apply to the highest-fit current role."

    return {
        "schema": "career_weekly_roi_summary_v1",
        "generated_at": utc_now_iso(),
        "applications": {
            "submitted": submitted,
            "interviews": interviews,
            "interview_rate": interviews / submitted if submitted else 0.0,
            "missing_outcome": missing_outcome,
            "best_sources": best_sources[:3],
            "worst_sources": worst_sources[:3],
        },
        "recruiters": {
            "sent": len(recruiter_sent),
            "missing_accepted_at": missing_accepted_at,
            "missing_reply_at": missing_reply_at,
            "missing_interview_at": missing_interview_at,
        },
        "next_roi_action": next_action,
    }


def record_opportunity_action(
    *,
    action_type: str,
    opportunity_id: str,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
    packs_dir: Path = PACKS_DIR,
    applications_csv: Path = APPLICATIONS_CSV,
    application_url: str = "",
    operator_source: str = "dashboard",
) -> dict[str, Any]:
    if action_type not in SAFE_OPPORTUNITY_ACTIONS:
        raise ValueError(f"Unsupported opportunity action: {action_type}")
    opportunity = get_opportunity(opportunity_id, db_path=db_path)
    if opportunity is None:
        raise ValueError(f"Opportunity not found: {opportunity_id}")

    old_status = opportunity.status
    metadata: dict[str, Any] = {}
    if action_type == "mark_review":
        opportunity.status = OpportunityStatus.REVIEW
    elif action_type == "mark_skipped":
        opportunity.status = OpportunityStatus.SKIPPED
    elif action_type == "mark_apply_ready":
        opportunity.status = OpportunityStatus.APPLY_READY
    elif action_type == "mark_applied":
        opportunity.status = OpportunityStatus.APPLIED
    elif action_type == "log_application":
        opportunity.status = OpportunityStatus.APPLIED
        metadata = _append_application_log(
            opportunity,
            applications_csv=applications_csv,
            application_url=application_url,
        )
    elif action_type == "snooze_followup":
        opportunity.status = OpportunityStatus.FOLLOW_UP
    elif action_type == "generate_pack":
        if opportunity.status != OpportunityStatus.APPLY_READY:
            raise ValueError("Only apply-ready opportunities can generate packs.")
        metadata = _generate_pack(opportunity, packs_dir=packs_dir)

    opportunity.next_action = next_action_for_opportunity(opportunity)
    save_opportunity(opportunity, db_path=db_path)
    event = record_action(
        opportunity=opportunity,
        action_type=action_type,
        old_status=old_status,
        operator_source=operator_source,
        metadata=metadata,
        db_path=db_path,
    )
    return {
        "ok": True,
        "opportunity_id": opportunity.opportunity_id,
        "action_type": action_type,
        **metadata,
        "event": event,
    }


def json_response(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.cmd == "overview":
        return build_opportunity_overview()
    if args.cmd == "detail":
        return build_opportunity_detail(args.opportunity_id)
    if args.cmd == "weekly-roi":
        return build_weekly_roi_summary()
    if args.cmd == "action":
        return record_opportunity_action(
            action_type=args.name,
            opportunity_id=args.opportunity_id,
            application_url=args.application_url,
        )
    raise ValueError(f"Unsupported command: {args.cmd}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Opportunity dashboard JSON helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("overview")
    detail = sub.add_parser("detail")
    detail.add_argument("--opportunity-id", required=True)
    sub.add_parser("weekly-roi")
    action = sub.add_parser("action")
    action.add_argument("--name", required=True, choices=SAFE_OPPORTUNITY_ACTIONS)
    action.add_argument("--opportunity-id", required=True)
    action.add_argument("--application-url", default="")
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
