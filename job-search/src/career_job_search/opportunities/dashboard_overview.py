"""Opportunity dashboard summaries, saved views, details, and exports."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from career_job_search.opportunities.alerts import ALERT_LIVE_WINDOW_HOURS
from career_job_search.opportunities.browser import BROWSER_LIVE_WINDOW_HOURS
from career_job_search.opportunities.dashboard_actions import SAFE_OPPORTUNITY_ACTIONS
from career_job_search.opportunities.dashboard_common import (
    APPLICATIONS_CSV,
    VILNIUS_TIMEZONE,
    opportunity_record,
)
from career_job_search.opportunities.dashboard_common import (
    csv_rows as _csv_rows,
)
from career_job_search.opportunities.dashboard_common import (
    date_from_iso as _date_from_iso,
)
from career_job_search.opportunities.dashboard_common import (
    datetime_from_iso as _datetime_from_iso,
)
from career_job_search.opportunities.dashboard_common import (
    is_europe_fit as _is_europe_fit,
)
from career_job_search.opportunities.dashboard_common import (
    pipeline_stage as _pipeline_stage,
)
from career_job_search.opportunities.dashboard_common import (
    risk_flags as _risk_flags,
)
from career_job_search.opportunities.dashboard_common import (
    risk_groups as _risk_groups,
)
from career_job_search.opportunities.models import (
    utc_now_iso,
)
from career_job_search.opportunities.preferences import (
    DEFAULT_SEARCH_PREFERENCES_PATH,
    SearchPreferences,
    default_search_preferences,
    load_search_preferences,
)
from career_job_search.opportunities.repository import (
    DEFAULT_OPPORTUNITY_DB,
    get_opportunity,
    latest_daily_run,
    list_opportunities,
)

BEST_MATCH_BLOCKING_FLAGS = {
    "duplicate",
    "likely_closed",
    "low_cv_score",
    "needs_live_verification",
    "possible_scam",
    "possible_duplicate",
    "vague_role",
    "watchlist_only",
    "weak_location_fit",
    "location_ineligible",
    "language_requirement_risk",
    "remote_eligibility_unverified",
    "role_family_mismatch",
    "visa_location_risk",
}

def _annotate_possible_duplicates(rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(
            re.sub(r"[^a-z0-9]+", " ", str(row.get(field) or "").casefold()).strip()
            for field in ("company", "title", "location")
        )
        if key[0] and key[1]:
            groups.setdefault(key, []).append(row)
    for grouped_rows in groups.values():
        if len(grouped_rows) < 2:
            continue
        preferred = max(
            grouped_rows,
            key=lambda row: (
                row.get("live_status") == "live",
                str(row.get("live_checked_at") or ""),
                str(row.get("source_updated_at") or ""),
                str(row.get("last_seen_at") or ""),
            ),
        )
        for row in grouped_rows:
            if row is preferred:
                continue
            evidence = row.setdefault("evidence", {})
            flags = list(evidence.get("risk_flags") or [])
            if "possible_duplicate" not in flags:
                flags.append("possible_duplicate")
            evidence["risk_flags"] = flags


def _opportunity_summary(row: dict[str, Any]) -> dict[str, Any]:
    match = row.get("match") or {}
    risk = _risk_groups(row)
    return {
        "opportunity_id": row.get("opportunity_id"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "source_kind": row.get("source_kind"),
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "location_eligibility": row.get("location_eligibility"),
        "eligibility_reason": row.get("eligibility_reason"),
        "salary_text": row.get("salary_text"),
        "deadline": row.get("deadline"),
        "first_seen_at": row.get("first_seen_at"),
        "source_updated_at": row.get("source_updated_at"),
        "live_status": row.get("live_status"),
        "live_checked_at": row.get("live_checked_at"),
        "live_check_note": row.get("live_check_note"),
        "likely_closed": bool(row.get("likely_closed")),
        "status": row.get("status"),
        "stage": _pipeline_stage(row),
        "next_action": row.get("next_action"),
        "has_pack": bool(row.get("pack")),
        "preference": row.get("preference")
        or {
            "eligible": True,
            "score": 0,
            "reasons": ["Recommended from CV fit and current role evidence"],
            "flags": [],
        },
        "evidence": {
            "risk_flags": _risk_flags(row),
            "confidence": (row.get("evidence") or {}).get("confidence", 0),
            **risk,
        },
        "match": (
            {
                "best_variant": match.get("best_variant"),
                "score": match.get("score", 0),
                "fit_score": match.get("fit_score", 0),
                "cv_score": match.get("cv_score", 0),
                "role_track": match.get("role_track"),
                "confidence": match.get("confidence"),
            }
            if match
            else None
        ),
    }


def _is_actionable_review(row: dict[str, Any]) -> bool:
    if row.get("status") != "review":
        return False
    if _pipeline_stage(row) == "closed":
        return False
    if _risk_groups(row)["blockers"]:
        return False
    if "low_cv_score" in _risk_flags(row) or _match_score(row) < 8:
        return False
    return str(row.get("location_eligibility") or "") in {
        "eligible_vilnius",
        "eligible_lt_remote",
        "eligible_eu_remote",
        "verify_remote",
    }


def _is_clean_best_match(row: dict[str, Any]) -> bool:
    flags = set(_risk_flags(row))
    return not flags.intersection(BEST_MATCH_BLOCKING_FLAGS)


def _has_fresh_live_evidence(row: dict[str, Any]) -> bool:
    checked = _datetime_from_iso(str(row.get("live_checked_at") or ""))
    if row.get("live_status") != "live" or checked is None:
        return False
    live_window_hours = (
        ALERT_LIVE_WINDOW_HOURS
        if row.get("live_check_method") == "official_job_alert"
        else BROWSER_LIVE_WINDOW_HOURS
    )
    age = datetime.now(UTC) - checked
    if not timedelta(0) <= age <= timedelta(hours=live_window_hours):
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
        and row.get("status") in {"review", "matched", "apply_ready"}
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


def _has_usable_cv_match(row: dict[str, Any]) -> bool:
    match = row.get("match") or {}
    try:
        cv_score = float(match.get("cv_score") or 0.0)
        margin = float(match.get("margin_over_second") or 0.0)
    except (TypeError, ValueError):
        return False
    if cv_score < 10.0:
        return False
    confidence = str(match.get("confidence") or "")
    return confidence == "clear_winner" and margin >= 5.0 or confidence == "tie_review"


def _is_top_today_candidate(row: dict[str, Any]) -> bool:
    if row.get("status") not in {"review", "matched", "apply_ready"}:
        return False
    if (
        not bool((row.get("preference") or {}).get("eligible", True))
        or (row.get("preference") or {}).get("flags")
        and "work_arrangement_not_selected"
        in set((row.get("preference") or {}).get("flags") or [])
        or
        not _is_europe_fit(row)
        or not _is_clean_best_match(row)
        or not _has_fresh_live_evidence(row)
        or not _has_usable_cv_match(row)
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


def _top_today_sort_key(row: dict[str, Any]) -> tuple[float, int, int, str]:
    action_priority = {
        "make_pack": 3,
        "apply_manual": 3,
        "tailor_cv": 2,
        "review": 1,
    }.get(str(row.get("next_action") or ""), 0)
    preference_score = int((row.get("preference") or {}).get("score") or 0)
    return (
        _match_score(row),
        preference_score,
        action_priority,
        str(row.get("company") or ""),
    )


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


def _latest_applications(
    applications: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for application in applications:
        opportunity_id = (application.get("opportunity_id") or "").strip()
        if not opportunity_id:
            continue
        existing = latest.get(opportunity_id)
        if existing is None or (application.get("date_iso") or "") >= (
            existing.get("date_iso") or ""
        ):
            latest[opportunity_id] = application
    return latest


def _missing_application_outcome(
    row: dict[str, Any], latest: dict[str, dict[str, str]]
) -> bool:
    opportunity_id = str(row.get("opportunity_id") or "")
    application = latest.get(opportunity_id)
    if application:
        return (application.get("outcome") or "").strip().lower() in {"", "applied"}
    return row.get("status") == "applied"


def _follow_up_due(
    row: dict[str, Any], latest: dict[str, dict[str, str]], today: date
) -> bool:
    if row.get("status") == "follow_up":
        return True
    application = latest.get(str(row.get("opportunity_id") or ""))
    if not application or (application.get("response_date") or "").strip():
        return False
    submitted = _date_from_iso(application.get("date_iso") or "")
    outcome = (application.get("outcome") or "").strip().lower()
    return bool(
        submitted
        and outcome in {"", "applied"}
        and submitted <= today - timedelta(days=7)
    )


def _saved_views(
    rows: list[dict[str, Any]],
    applications: list[dict[str, str]] | None = None,
    *,
    daily_queue_size: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    today = datetime.now(VILNIUS_TIMEZONE).date()
    closing_cutoff = today + timedelta(days=14)
    latest_applications = _latest_applications(applications or [])
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
        "needs_review": [row for row in rows if _is_actionable_review(row)],
        "apply_ready": [row for row in rows if row.get("status") == "apply_ready"],
        "needs_cv_tailoring": [
            row
            for row in rows
            if row.get("next_action") == "tailor_cv"
            and not _risk_groups(row)["blockers"]
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
        "missing_outcome": [
            row
            for row in rows
            if _missing_application_outcome(row, latest_applications)
        ],
        "follow_up": [
            row for row in rows if _follow_up_due(row, latest_applications, today)
        ],
        "skipped": [row for row in rows if row.get("status") == "skipped"],
        "expired": [row for row in rows if row.get("status") == "expired"],
        "likely_duplicate": [
            row
            for row in rows
            if {"duplicate", "possible_duplicate"}.intersection(_risk_flags(row))
        ],
        "likely_expired": [
            row
            for row in rows
            if row.get("likely_closed") or row.get("status") == "expired"
        ],
        "risk_flags": [
            row
            for row in rows
            if _risk_groups(row)["blockers"] or _risk_groups(row)["warnings"]
        ],
        "blockers": [row for row in rows if _risk_groups(row)["blockers"]],
        "warnings": [row for row in rows if _risk_groups(row)["warnings"]],
        "stage_new": [row for row in rows if _pipeline_stage(row) == "new"],
        "stage_review": [row for row in rows if _pipeline_stage(row) == "review"],
        "stage_shortlisted": [
            row for row in rows if _pipeline_stage(row) == "shortlisted"
        ],
        "stage_pack_ready": [
            row for row in rows if _pipeline_stage(row) == "pack_ready"
        ],
        "stage_applied": [row for row in rows if _pipeline_stage(row) == "applied"],
        "stage_follow_up": [row for row in rows if _pipeline_stage(row) == "follow_up"],
        "stage_closed": [row for row in rows if _pipeline_stage(row) == "closed"],
    }
    top_candidates: dict[str, dict[str, Any]] = {}
    for row in (
        *views["apply_today"],
        *views["best_europe_matches"],
        *views["needs_cv_tailoring"],
        *views["needs_review"],
    ):
        if _is_top_today_candidate(row):
            top_candidates[str(row["opportunity_id"])] = row
    ranked_today = sorted(
        top_candidates.values(),
        key=_top_today_sort_key,
        reverse=True,
    )
    views["daily_queue"] = ranked_today[:daily_queue_size]
    # Keep the legacy view stable for scripts and saved links while the web app
    # moves to the configurable Daily Queue.
    views["top_5_today"] = ranked_today[:5]
    return views


def _overview_search_preferences(
    *,
    db_path: Path | str,
    search_preferences: SearchPreferences | None,
) -> SearchPreferences:
    if search_preferences is not None:
        return search_preferences
    try:
        if Path(db_path).resolve() == Path(DEFAULT_OPPORTUNITY_DB).resolve():
            return load_search_preferences(DEFAULT_SEARCH_PREFERENCES_PATH)
    except OSError:
        pass
    return default_search_preferences()


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
    applications_csv: Path = APPLICATIONS_CSV,
    search_preferences: SearchPreferences | None = None,
) -> dict[str, Any]:
    preferences = _overview_search_preferences(
        db_path=db_path,
        search_preferences=search_preferences,
    )
    opportunities = list_opportunities(db_path=db_path)
    rows = [
        opportunity_record(
            row,
            db_path=db_path,
            applications_csv=applications_csv,
            include_application_history=False,
            search_preferences=preferences,
        )
        for row in opportunities
    ]
    _annotate_possible_duplicates(rows)
    saved_views = _saved_views(
        rows,
        _csv_rows(Path(applications_csv)),
        daily_queue_size=preferences.daily_queue_size,
    )
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
    summary_rows = [_opportunity_summary(row) for row in rows]
    saved_view_ids = {
        name: [str(row.get("opportunity_id") or "") for row in view_rows]
        for name, view_rows in saved_views.items()
    }
    role_fit_rows = [
        row
        for row in rows
        if "role_family_mismatch" not in _risk_flags(row) and _match_score(row) >= 8
    ]
    location_fit_rows = [
        row
        for row in rows
        if str(row.get("location_eligibility") or "")
        in {
            "eligible_vilnius",
            "eligible_lt_remote",
            "eligible_eu_remote",
            "verify_remote",
        }
    ]
    return {
        "schema": "opportunity_dashboard_overview_v2",
        "generated_at": utc_now_iso(),
        "counts": {
            "total": len(rows),
            "new_today": len(saved_views["new_today"]),
            "fresh_live_matches": len(saved_views["fresh_live_matches"]),
            "updated_roles": len(saved_views["updated_roles"]),
            "closing_soon": len(saved_views["closing_soon"]),
            "top_5_today": len(saved_views["top_5_today"]),
            "daily_queue": len(saved_views["daily_queue"]),
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
            "blockers": len(saved_views["blockers"]),
            "warnings": len(saved_views["warnings"]),
        },
        "funnel": {
            "discovered": len(rows),
            "deduplicated": len(rows) - len(saved_views["likely_duplicate"]),
            "location_fit": len(location_fit_rows),
            "role_fit": len(role_fit_rows),
            "shortlisted": len(saved_views["stage_shortlisted"]),
            "apply_ready": len(saved_views["apply_ready"]),
        },
        "pipeline": {
            "new": len(saved_views["stage_new"]),
            "review": len(saved_views["stage_review"]),
            "shortlisted": len(saved_views["stage_shortlisted"]),
            "pack_ready": len(saved_views["stage_pack_ready"]),
            "applied": len(saved_views["stage_applied"]),
            "follow_up": len(saved_views["stage_follow_up"]),
            "closed": len(saved_views["stage_closed"]),
        },
        "queues": {
            "all": summary_rows,
            "saved_views": saved_view_ids,
        },
        "search_profile": {
            "daily_queue_size": preferences.daily_queue_size,
            "updated_at": preferences.updated_at,
        },
        "safe_actions": SAFE_OPPORTUNITY_ACTIONS,
    }


def build_opportunity_detail(
    opportunity_id: str,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
    applications_csv: Path = APPLICATIONS_CSV,
    search_preferences: SearchPreferences | None = None,
) -> dict[str, Any]:
    opportunity = get_opportunity(opportunity_id, db_path=db_path)
    if opportunity is None:
        raise ValueError(f"Opportunity not found: {opportunity_id}")
    return opportunity_record(
        opportunity,
        db_path=db_path,
        applications_csv=applications_csv,
        search_preferences=_overview_search_preferences(
            db_path=db_path,
            search_preferences=search_preferences,
        ),
    )


def build_opportunity_export(
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
    applications_csv: Path = APPLICATIONS_CSV,
) -> dict[str, Any]:
    applications = _csv_rows(Path(applications_csv))
    applications_by_id: dict[str, list[dict[str, str]]] = {}
    for application in applications:
        opportunity_id = (application.get("opportunity_id") or "").strip()
        if opportunity_id:
            applications_by_id.setdefault(opportunity_id, []).append(application)
    opportunities: list[dict[str, Any]] = []
    for opportunity in list_opportunities(db_path=db_path):
        row = opportunity_record(
            opportunity,
            db_path=db_path,
            applications_csv=applications_csv,
            include_application_history=False,
        )
        row["application_history"] = applications_by_id.get(
            opportunity.opportunity_id,
            [],
        )
        opportunities.append(row)
    return {
        "schema": "career_opportunity_export_v1",
        "generated_at": utc_now_iso(),
        "opportunities": opportunities,
        "applications": applications,
    }
