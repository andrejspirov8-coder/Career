from __future__ import annotations

import csv
from pathlib import Path

import pytest

from career_job_search.cvs import performance as vp  # noqa: E402


def test_analyse_by_variant_counts_and_rates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "applications.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["variant_slug", "source", "outcome"])
        writer.writeheader()
        writer.writerow({"variant_slug": "luxury-retail", "source": "linkedin", "outcome": "applied"})
        writer.writerow({"variant_slug": "luxury-retail", "source": "linkedin", "outcome": "interview"})
    monkeypatch.setattr(vp, "APPLICATIONS_CSV", csv_path)
    results = vp.analyse_by_variant(vp.load_applications())
    assert results["luxury-retail"]["submitted"] == 2
    assert results["luxury-retail"]["interview_rate"] == pytest.approx(0.5)


def test_analyse_roi_groups_tailoring_score_and_response_days() -> None:
    rows = [
        {
            "variant_slug": "business-process-operations",
            "source": "linkedin",
            "outcome": "interview",
            "match_score": "18.0",
            "tailored_cv": "yes",
            "date_iso": "2026-05-01",
            "response_date": "2026-05-04",
        },
        {
            "variant_slug": "business-process-operations",
            "source": "cvbank",
            "outcome": "applied",
            "match_score": "9.0",
            "tailored_cv": "no",
            "date_iso": "2026-05-02",
            "response_date": "",
        },
    ]

    results = vp.analyse_roi(rows)

    assert results["tailored_cv"]["tailored_yes"]["interview_rate"] == pytest.approx(1.0)
    assert results["tailored_cv"]["tailored_yes"]["avg_response_days"] == pytest.approx(3.0)
    assert results["match_score"]["high_score_15_plus"]["submitted"] == 1
    assert results["match_score"]["lower_score_under_15"]["submitted"] == 1


def test_load_applications_keeps_opportunity_tracking_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "applications.csv"
    csv_path.write_text(
        (
            "date_iso,company,title,variant_slug,source,outcome,deadline_date,"
            "match_score,match_confidence,salary_range,tailored_cv,response_date,"
            "opportunity_id,pack_dir,application_url,notes\n"
            "2026-06-30,Vinted,Operations Manager,operations-management,"
            "company_site,applied,,18.0,clear_winner,,yes,,opp_123,"
            "/tmp/pack,https://example.com/apply,Applied manually\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(vp, "APPLICATIONS_CSV", csv_path)

    rows = vp.load_applications()

    assert rows[0]["opportunity_id"] == "opp_123"
    assert rows[0]["pack_dir"] == "/tmp/pack"
    assert rows[0]["application_url"] == "https://example.com/apply"
