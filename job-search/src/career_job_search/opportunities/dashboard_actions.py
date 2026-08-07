"""Human-reviewed opportunity actions and outcome reporting."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from career_job_search.core.paths import project_path
from career_job_search.cvs.matching import load_profiles
from career_job_search.opportunities.dashboard_common import (
    APPLICATIONS_CSV,
    RECRUITERS_CSV,
)
from career_job_search.opportunities.dashboard_common import (
    csv_rows as _csv_rows,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityPack,
    OpportunityStatus,
    next_action_for_opportunity,
    utc_now_iso,
)
from career_job_search.opportunities.packs import write_pack_files
from career_job_search.opportunities.repository import (
    DEFAULT_OPPORTUNITY_DB,
    actions_for_opportunity,
    get_opportunity,
    record_action,
    save_opportunity,
)

PACKS_DIR = project_path("packs")
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
    "update_application_outcome",
    "snooze_followup",
    "undo_last_decision",
]
APPLICATION_OUTCOMES = {"screening", "interview", "offer", "rejected", "withdrawn"}
SKIP_REASONS = {
    "not_relevant",
    "location",
    "salary",
    "seniority",
    "company",
    "duplicate",
    "closed",
    "other",
}
REVERSIBLE_DECISION_ACTIONS = {
    "mark_review",
    "mark_skipped",
    "mark_apply_ready",
    "snooze_followup",
}


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
    application_notes: str = "",
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
        "notes": application_notes.strip()
        or "Logged from opportunity queue; actual application submitted manually.",
    }


def _append_application_log(
    opportunity: Opportunity,
    *,
    applications_csv: Path = APPLICATIONS_CSV,
    application_url: str = "",
    application_notes: str = "",
) -> dict[str, Any]:
    path = Path(applications_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = _application_row(
        opportunity,
        application_url=application_url,
        application_notes=application_notes,
    )
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


def _update_application_outcome(
    opportunity: Opportunity,
    *,
    outcome: str,
    applications_csv: Path = APPLICATIONS_CSV,
) -> dict[str, Any]:
    clean_outcome = outcome.strip().lower()
    if clean_outcome not in APPLICATION_OUTCOMES:
        raise ValueError("Choose a valid application outcome.")
    path = Path(applications_csv)
    rows = _csv_rows(path)
    matching_indexes = [
        index
        for index, row in enumerate(rows)
        if (row.get("opportunity_id") or "").strip() == opportunity.opportunity_id
    ]
    if not matching_indexes:
        raise ValueError("Log the application before recording an outcome.")
    index = matching_indexes[-1]
    rows[index]["outcome"] = clean_outcome
    rows[index]["response_date"] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=APPLICATION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
    return {
        "application_updated": True,
        "application_csv": str(path),
        "outcome": clean_outcome,
        "response_date": rows[index]["response_date"],
    }


def _preference_suggestion(
    opportunity: Opportunity,
    *,
    decision_reason: str,
) -> dict[str, str] | None:
    if decision_reason == "company" and opportunity.company.strip():
        return {
            "kind": "add_excluded_company",
            "value": opportunity.company.strip(),
            "label": f"Exclude {opportunity.company.strip()} from future daily queues",
        }
    if decision_reason == "not_relevant":
        role_track = opportunity.match.role_track.strip() if opportunity.match else ""
        value = role_track.replace("_", " ") or opportunity.title.strip()
        if value:
            return {
                "kind": "add_excluded_keyword",
                "value": value[:80],
                "label": f"Exclude roles matching “{value[:80]}”",
            }
    return None


def _undo_last_decision(
    opportunity: Opportunity,
    *,
    db_path: Path | str,
) -> dict[str, Any]:
    history = actions_for_opportunity(opportunity.opportunity_id, db_path=db_path)
    if not history:
        raise ValueError("There is no decision to undo for this role.")
    latest = history[0]
    action_type = str(latest.get("action_type") or "")
    if action_type not in REVERSIBLE_DECISION_ACTIONS:
        raise ValueError(
            "The latest action has file or application side effects and cannot be undone safely."
        )
    current_status = opportunity.status.value
    if current_status != str(latest.get("new_status") or ""):
        raise ValueError(
            "This role changed after that decision, so it cannot be undone safely."
        )
    old_status = str(latest.get("old_status") or "")
    try:
        opportunity.status = OpportunityStatus(old_status)
    except ValueError as exc:
        raise ValueError(
            "The previous role status is invalid and cannot be restored."
        ) from exc
    return {
        "undone_action": action_type,
        "restored_status": opportunity.status.value,
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
    application_notes: str = "",
    application_outcome: str = "",
    decision_reason: str = "",
    decision_note: str = "",
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
        clean_reason = decision_reason.strip().lower() or "other"
        if clean_reason not in SKIP_REASONS:
            raise ValueError("Choose a valid reason for closing this role.")
        clean_note = decision_note.strip()
        if len(clean_note) > 500:
            raise ValueError("Decision notes must be 500 characters or fewer.")
        opportunity.status = OpportunityStatus.SKIPPED
        metadata = {
            "decision_reason": clean_reason,
            "decision_note": clean_note,
        }
        suggestion = _preference_suggestion(
            opportunity,
            decision_reason=clean_reason,
        )
        if suggestion:
            metadata["preference_suggestion"] = suggestion
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
            application_notes=application_notes,
        )
    elif action_type == "update_application_outcome":
        metadata = _update_application_outcome(
            opportunity,
            outcome=application_outcome,
            applications_csv=applications_csv,
        )
        clean_outcome = application_outcome.strip().lower()
        if clean_outcome in {"screening", "interview", "offer"}:
            opportunity.status = OpportunityStatus.FOLLOW_UP
        elif clean_outcome in {"rejected", "withdrawn"}:
            opportunity.status = OpportunityStatus.SKIPPED
    elif action_type == "snooze_followup":
        opportunity.status = OpportunityStatus.FOLLOW_UP
    elif action_type == "undo_last_decision":
        metadata = _undo_last_decision(opportunity, db_path=db_path)
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
        "can_undo": action_type in REVERSIBLE_DECISION_ACTIONS,
        **metadata,
        "event": event,
    }
