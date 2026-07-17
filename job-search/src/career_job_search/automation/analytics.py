#!/usr/bin/env python3
"""Aggregate private job-search outcomes into decision-useful analytics."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT

APPLICATIONS_CSV = JOB_ROOT / "pipeline" / "applications.csv"
RECRUITERS_CSV = JOB_ROOT / "pipeline" / "recruiters.csv"
SUBMITTED_OUTCOMES = {
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
}
RESPONSE_OUTCOMES = {"screening", "interview", "offer", "rejected"}
INTERVIEW_OUTCOMES = {"interview", "offer"}
MIN_RELIABLE_SAMPLE = 10


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader) if reader.fieldnames else []
    except (OSError, csv.Error):
        return []


def _clean(value: Any, fallback: str = "Unknown") -> str:
    text = str(value or "").strip()
    return text[:100] if text else fallback


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _response_days(row: dict[str, str]) -> int | None:
    submitted = _date(row.get("date_iso"))
    response = _date(row.get("response_date"))
    if submitted is None or response is None:
        return None
    days = (response - submitted).days
    return days if days >= 0 else None


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _sample_status(submitted: int) -> str:
    if submitted >= MIN_RELIABLE_SAMPLE:
        return "ready"
    if submitted >= 3:
        return "early"
    return "insufficient"


def _group_performance(rows: list[dict[str, str]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        outcome = _clean(row.get("outcome"), "").lower()
        if outcome in SUBMITTED_OUTCOMES:
            groups[_clean(row.get(field))].append(row)

    output = []
    for label, group in groups.items():
        outcomes = [_clean(row.get("outcome"), "").lower() for row in group]
        responses = sum(outcome in RESPONSE_OUTCOMES for outcome in outcomes)
        interviews = sum(outcome in INTERVIEW_OUTCOMES for outcome in outcomes)
        offers = sum(outcome == "offer" for outcome in outcomes)
        response_days = [
            days for row in group if (days := _response_days(row)) is not None
        ]
        output.append(
            {
                "label": label,
                "submitted": len(group),
                "responses": responses,
                "interviews": interviews,
                "offers": offers,
                "response_rate": _rate(responses, len(group)),
                "interview_rate": _rate(interviews, len(group)),
                "avg_response_days": (
                    sum(response_days) / len(response_days) if response_days else None
                ),
                "sample_status": _sample_status(len(group)),
                "needed_for_reliable_sample": max(0, MIN_RELIABLE_SAMPLE - len(group)),
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["sample_status"] == "ready",
            row["interview_rate"],
            row["submitted"],
            row["label"],
        ),
        reverse=True,
    )


def _trend(rows: list[dict[str, str]], *, today: date) -> list[dict[str, Any]]:
    current_monday = today - timedelta(days=today.weekday())
    weeks = [current_monday - timedelta(weeks=offset) for offset in range(7, -1, -1)]
    buckets = {
        week: {"week_start": week.isoformat(), "submitted": 0, "interviews": 0}
        for week in weeks
    }
    for row in rows:
        submitted_date = _date(row.get("date_iso"))
        if submitted_date is None:
            continue
        week = submitted_date - timedelta(days=submitted_date.weekday())
        if week not in buckets:
            continue
        outcome = _clean(row.get("outcome"), "").lower()
        if outcome in SUBMITTED_OUTCOMES:
            buckets[week]["submitted"] += 1
        if outcome in INTERVIEW_OUTCOMES:
            buckets[week]["interviews"] += 1
    return list(buckets.values())


def _recruiter_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    sent_statuses = {"sent", "pending", "accepted", "replied", "interview"}
    sent = [
        row
        for row in rows
        if _clean(row.get("status"), "").lower() in sent_statuses
        or any(
            _clean(row.get(field), "")
            for field in ("accepted_at", "reply_at", "interview_at")
        )
    ]
    accepted = sum(bool(_clean(row.get("accepted_at"), "")) for row in sent)
    replies = sum(bool(_clean(row.get("reply_at"), "")) for row in sent)
    interviews = sum(bool(_clean(row.get("interview_at"), "")) for row in sent)
    return {
        "profiles_logged": len(rows),
        "sent": len(sent),
        "accepted": accepted,
        "replies": replies,
        "interviews": interviews,
        "accept_rate": _rate(accepted, len(sent)),
        "reply_rate": _rate(replies, len(sent)),
        "interview_rate": _rate(interviews, len(sent)),
        "sample_status": _sample_status(len(sent)),
    }


def _recommendations(
    *,
    submitted: int,
    missing_outcome: int,
    by_source: list[dict[str, Any]],
    recruiters: dict[str, Any],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if missing_outcome:
        recommendations.append(
            {
                "priority": "high",
                "title": "Update application outcomes",
                "message": f"{missing_outcome} application{'s are' if missing_outcome != 1 else ' is'} still marked only as applied or blank.",
            }
        )
    if submitted == 0:
        recommendations.append(
            {
                "priority": "normal",
                "title": "Log the first manual application",
                "message": "Insights start becoming useful after outcomes are recorded in the Applications workspace.",
            }
        )
    elif submitted < MIN_RELIABLE_SAMPLE:
        recommendations.append(
            {
                "priority": "normal",
                "title": "Treat current rates as an early signal",
                "message": f"Log {MIN_RELIABLE_SAMPLE - submitted} more application{'s' if MIN_RELIABLE_SAMPLE - submitted != 1 else ''} before comparing conversion rates confidently.",
            }
        )
    reliable_sources = [row for row in by_source if row["sample_status"] == "ready"]
    if reliable_sources:
        best = max(
            reliable_sources,
            key=lambda row: (row["interview_rate"], row["response_rate"]),
        )
        recommendations.append(
            {
                "priority": "opportunity",
                "title": f"Protect time for {best['label']}",
                "message": f"It has the strongest interview rate among sources with at least {MIN_RELIABLE_SAMPLE} applications.",
            }
        )
    if recruiters["sent"] and recruiters["sample_status"] != "ready":
        recommendations.append(
            {
                "priority": "normal",
                "title": "Recruiter outreach is still a small sample",
                "message": f"Record outcomes for {MIN_RELIABLE_SAMPLE - recruiters['sent']} more sent contact{'s' if MIN_RELIABLE_SAMPLE - recruiters['sent'] != 1 else ''} before changing the outreach strategy.",
            }
        )
    return recommendations[:4]


def build_analytics(
    *,
    applications_csv: Path = APPLICATIONS_CSV,
    recruiters_csv: Path = RECRUITERS_CSV,
    today: date | None = None,
) -> dict[str, Any]:
    application_rows = _rows(Path(applications_csv))
    recruiter_rows = _rows(Path(recruiters_csv))
    outcomes = [_clean(row.get("outcome"), "").lower() for row in application_rows]
    submitted = sum(outcome in SUBMITTED_OUTCOMES for outcome in outcomes)
    responses = sum(outcome in RESPONSE_OUTCOMES for outcome in outcomes)
    screenings = sum(
        outcome in {"screening", "interview", "offer"} for outcome in outcomes
    )
    interviews = sum(outcome in INTERVIEW_OUTCOMES for outcome in outcomes)
    offers = sum(outcome == "offer" for outcome in outcomes)
    missing_outcome = sum(outcome in {"", "applied"} for outcome in outcomes)
    response_days = [
        days for row in application_rows if (days := _response_days(row)) is not None
    ]
    by_source = _group_performance(application_rows, "source")
    by_variant = _group_performance(application_rows, "variant_slug")
    recruiters = _recruiter_summary(recruiter_rows)
    current_day = today or datetime.now(UTC).date()
    return {
        "schema": "career_analytics_overview_v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "funnel": {
            "logged": len(application_rows),
            "submitted": submitted,
            "responses": responses,
            "screenings_or_better": screenings,
            "interviews_or_better": interviews,
            "offers": offers,
            "rejected": sum(outcome == "rejected" for outcome in outcomes),
            "withdrawn": sum(outcome == "withdrawn" for outcome in outcomes),
            "response_rate": _rate(responses, submitted),
            "interview_rate": _rate(interviews, submitted),
            "offer_rate": _rate(offers, submitted),
            "avg_response_days": (
                sum(response_days) / len(response_days) if response_days else None
            ),
        },
        "data_quality": {
            "missing_outcome": missing_outcome,
            "outcome_coverage_rate": _rate(
                len(application_rows) - missing_outcome, len(application_rows)
            ),
            "reliable_sample": submitted >= MIN_RELIABLE_SAMPLE,
            "minimum_reliable_sample": MIN_RELIABLE_SAMPLE,
        },
        "by_source": by_source,
        "by_variant": by_variant,
        "weekly_trend": _trend(application_rows, today=current_day),
        "recruiters": recruiters,
        "recommendations": _recommendations(
            submitted=submitted,
            missing_outcome=missing_outcome,
            by_source=by_source,
            recruiters=recruiters,
        ),
        "privacy": {
            "aggregate_only": True,
            "includes_descriptions": False,
            "message": "Only local counts and category labels are returned; job descriptions and notes are excluded.",
        },
    }


def json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career outcome analytics")
    parser.add_argument("overview", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        data = build_analytics()
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": data})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
