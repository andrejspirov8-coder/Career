"""Shared dashboard record formatting and risk classification."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from career_job_search.core.paths import project_path
from career_job_search.opportunities.models import Opportunity
from career_job_search.opportunities.preferences import (
    SearchPreferences,
    evaluate_search_preferences,
)
from career_job_search.opportunities.repository import (
    DEFAULT_OPPORTUNITY_DB,
    actions_for_opportunity,
)
from career_job_search.opportunities.text import clean_opportunity_text

APPLICATIONS_CSV = project_path("pipeline", "applications.csv")
RECRUITERS_CSV = project_path("pipeline", "recruiters.csv")
VILNIUS_TIMEZONE = ZoneInfo("Europe/Vilnius")

BLOCKING_RISK_FLAGS = {
    "duplicate",
    "likely_closed",
    "location_ineligible",
    "language_requirement_risk",
    "missing_company",
    "missing_title",
    "possible_scam",
    "role_family_mismatch",
    "visa_location_risk",
}
WARNING_RISK_FLAGS = {
    "link_review_required",
    "low_cv_score",
    "needs_live_verification",
    "possible_duplicate",
    "remote_eligibility_unverified",
    "vague_role",
    "weak_location_fit",
}
INFORMATIONAL_FLAGS = {"role_updated", "watchlist_only"}


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def date_from_iso(value: str) -> date | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(VILNIUS_TIMEZONE)
        return parsed.date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def datetime_from_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VILNIUS_TIMEZONE)
    return parsed.astimezone(UTC)


def is_europe_fit(row: dict[str, Any]) -> bool:
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


def risk_flags(row: dict[str, Any]) -> list[str]:
    return list((row.get("evidence") or {}).get("risk_flags") or [])


def risk_groups(row: dict[str, Any]) -> dict[str, list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    for flag in risk_flags(row):
        if flag in BLOCKING_RISK_FLAGS:
            blockers.append(flag)
        elif flag in INFORMATIONAL_FLAGS:
            info.append(flag)
        elif flag in WARNING_RISK_FLAGS:
            warnings.append(flag)
        else:
            warnings.append(flag)
    return {"blockers": blockers, "warnings": warnings, "info": info}


def pipeline_stage(row: dict[str, Any]) -> str:
    status = str(row.get("status") or "")
    if (
        status in {"skipped", "expired"}
        or row.get("live_status") == "closed"
        or row.get("likely_closed")
    ):
        return "closed"
    if status == "follow_up":
        return "follow_up"
    if status == "applied":
        return "applied"
    if status == "apply_ready":
        return "pack_ready" if row.get("pack") else "shortlisted"
    if status == "matched":
        return "shortlisted"
    if status == "review":
        return "review"
    return "new"


def opportunity_record(
    opportunity: Opportunity,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
    applications_csv: Path = APPLICATIONS_CSV,
    include_application_history: bool = True,
    search_preferences: SearchPreferences | None = None,
) -> dict[str, Any]:
    data = opportunity.to_json_dict()
    data["description"] = clean_opportunity_text(opportunity.description)
    data["action_history"] = actions_for_opportunity(
        opportunity.opportunity_id,
        db_path=db_path,
    )
    if include_application_history:
        data["application_history"] = [
            row
            for row in csv_rows(Path(applications_csv))
            if (row.get("opportunity_id") or "").strip() == opportunity.opportunity_id
        ]
    data["risk"] = risk_groups(data)
    data["stage"] = pipeline_stage(data)
    if search_preferences is not None:
        data["preference"] = evaluate_search_preferences(data, search_preferences)
    return data
