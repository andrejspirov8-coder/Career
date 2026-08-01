from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from career_job_search.automation.analytics import build_analytics


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_analytics_builds_funnel_groups_and_response_speed(tmp_path: Path) -> None:
    applications = tmp_path / "applications.csv"
    recruiters = tmp_path / "recruiters.csv"
    rows = [
        {
            "date_iso": "2026-07-01",
            "variant_slug": "operations-management",
            "source": "company_site",
            "outcome": "interview",
            "response_date": "2026-07-04",
        },
        {
            "date_iso": "2026-07-02",
            "variant_slug": "operations-management",
            "source": "company_site",
            "outcome": "applied",
            "response_date": "",
        },
        {
            "date_iso": "2026-07-03",
            "variant_slug": "luxury-retail",
            "source": "linkedin",
            "outcome": "offer",
            "response_date": "2026-07-08",
        },
    ]
    _write_csv(
        applications,
        ["date_iso", "variant_slug", "source", "outcome", "response_date"],
        rows,
    )
    _write_csv(
        recruiters,
        ["status", "accepted_at", "reply_at", "interview_at"],
        [
            {
                "status": "sent",
                "accepted_at": "2026-07-04",
                "reply_at": "2026-07-05",
                "interview_at": "",
            }
        ],
    )

    result = build_analytics(
        applications_csv=applications,
        recruiters_csv=recruiters,
        today=date(2026, 7, 15),
    )

    assert result["funnel"]["submitted"] == 3
    assert result["funnel"]["interviews_or_better"] == 2
    assert result["funnel"]["interview_rate"] == pytest.approx(2 / 3)
    assert result["funnel"]["avg_response_days"] == pytest.approx(4)
    assert result["data_quality"]["missing_outcome"] == 1
    assert result["by_source"][0]["sample_status"] == "insufficient"
    assert result["recruiters"]["reply_rate"] == pytest.approx(1.0)
    assert len(result["weekly_trend"]) == 8


def test_analytics_requires_ten_rows_before_reliable_comparisons(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "applications.csv"
    rows = [
        {
            "date_iso": f"2026-07-{index + 1:02d}",
            "variant_slug": "operations-management",
            "source": "company_site",
            "outcome": "interview" if index < 2 else "rejected",
            "response_date": "",
        }
        for index in range(10)
    ]
    _write_csv(
        applications,
        ["date_iso", "variant_slug", "source", "outcome", "response_date"],
        rows,
    )

    result = build_analytics(
        applications_csv=applications,
        recruiters_csv=tmp_path / "missing.csv",
        today=date(2026, 7, 15),
    )

    assert result["data_quality"]["reliable_sample"] is True
    assert result["by_source"][0]["sample_status"] == "ready"
    assert result["by_source"][0]["needed_for_reliable_sample"] == 0
    assert any("company_site" in row["title"] for row in result["recommendations"])


def test_empty_analytics_returns_guidance_without_private_records(
    tmp_path: Path,
) -> None:
    result = build_analytics(
        applications_csv=tmp_path / "missing-applications.csv",
        recruiters_csv=tmp_path / "missing-recruiters.csv",
        today=date(2026, 7, 15),
    )

    assert result["funnel"]["logged"] == 0
    assert result["recommendations"][0]["title"] == "Log the first manual application"
    assert result["privacy"]["includes_descriptions"] is False
