from __future__ import annotations

from datetime import date

import pytest

from career_job_search.opportunities.matching import (
    _has_hard_title_mismatch,
    deadline_score,
    location_score,
    risk_penalty,
    salary_score,
    source_score,
)
from career_job_search.opportunities.models import Opportunity, OpportunitySourceKind


def make_opportunity(
    source_kind: OpportunitySourceKind = OpportunitySourceKind.JOB_BOARD,
    title: str = "",
    salary_text: str = "",
    deadline: str = "",
    location: str = "",
    remote_policy: str = "",
    description: str = "",
) -> Opportunity:
    return Opportunity(
        source="test",
        source_kind=source_kind,
        title=title,
        salary_text=salary_text,
        deadline=deadline,
        location=location,
        remote_policy=remote_policy,
        description=description,
    )


# ── location_score ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("location", "remote_policy", "expected"),
    [
        ("Vilnius", "onsite", 6.0),
        ("Vilnius region", "hybrid", 6.0),
        ("Kaunas, Lithuania", "remote", 5.0),
        ("Remote EU", "remote", 5.0),
        ("New York, US", "onsite", 0.0),
        ("London, UK", "onsite", 0.0),
    ],
)
def test_location_score(location: str, remote_policy: str, expected: float) -> None:
    opp = make_opportunity(location=location, remote_policy=remote_policy)
    assert location_score(opp, None) == expected


# ── source_score ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source_kind", "expected"),
    [
        (OpportunitySourceKind.ATS, 3.0),
        (OpportunitySourceKind.COMPANY_SITE, 2.5),
        (OpportunitySourceKind.JOB_ALERT, 2.5),
        (OpportunitySourceKind.MANUAL_INBOX, 2.0),
        (OpportunitySourceKind.RECRUITER, 1.5),
        (OpportunitySourceKind.JOB_BOARD, 1.0),
        (OpportunitySourceKind.WEB_SEARCH, 1.0),
    ],
)
def test_source_score(source_kind: OpportunitySourceKind, expected: float) -> None:
    assert source_score(make_opportunity(source_kind=source_kind)) == expected


# ── salary_score ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("salary_text", "expected"),
    [
        ("", 0.0),
        ("   ", 0.0),
        ("Competitive", 1.0),
        ("3000-4000 EUR", pytest.approx(1.0 + 4000.0 / 5000.0)),
        ("2000-3000", pytest.approx(1.0 + 3000.0 / 5000.0)),
        ("100", 1.0),
        ("10", 1.0),
    ],
)
def test_salary_score(salary_text: str, expected: float | pytest.approx) -> None:
    assert salary_score(make_opportunity(salary_text=salary_text)) == expected


@pytest.mark.parametrize(
    ("salary_text", "expected"),
    [
        ("$4", 1.0),
        ("$43", 1.0),
        ("$38", 1.0),
        ("3,400-4,500 EUR gross/month", pytest.approx(1.0 + 4500.0 / 5000.0)),
        ("3.400-4.500 EUR gross/month", pytest.approx(1.0 + 4500.0 / 5000.0)),
        ("3,4 EUR", 1.0),
    ],
)
def test_salary_score_tiny_artifacts_not_boosted(
    salary_text: str, expected: float | pytest.approx
) -> None:
    assert salary_score(make_opportunity(salary_text=salary_text)) == expected


# ── deadline_score ──────────────────────────────────────────────────────────


def test_deadline_score_future() -> None:
    future = date(2099, 12, 31).isoformat()
    assert deadline_score(make_opportunity(deadline=future)) == 1.0


def test_deadline_score_past() -> None:
    past = date(2020, 1, 1).isoformat()
    assert deadline_score(make_opportunity(deadline=past)) == -2.0


def test_deadline_score_empty() -> None:
    assert deadline_score(make_opportunity(deadline="")) == 0.0


def test_deadline_score_invalid() -> None:
    assert deadline_score(make_opportunity(deadline="not-a-date")) == 0.0


# ── risk_penalty ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([], 0.0),
        (["possible_scam"], 8.0),
        (["role_family_mismatch"], 8.0),
        (["low_cv_score"], 5.0),
        (["weak_location_fit"], 3.0),
        (["needs_live_verification"], 3.0),
        (["language_requirement_risk"], 2.0),
        (["visa_location_risk"], 3.0),
        (["vague_role"], 2.0),
        (["duplicate"], 2.0),
        (["likely_closed"], 10.0),
        (["possible_scam", "low_cv_score", "vague_role"], 8.0 + 5.0 + 2.0),
    ],
)
def test_risk_penalty(flags: list[str], expected: float) -> None:
    assert risk_penalty(flags) == expected


def test_risk_penalty_unknown_flags() -> None:
    assert risk_penalty(["nonexistent_flag", "also_missing"]) == 0.0


# ── _has_hard_title_mismatch ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("", False),
        ("   ", False),
        ("Operations Manager", False),
        ("Customer Support Specialist", False),
        ("Data Engineer", True),
        ("Software Engineer", True),
        ("Senior Software Engineer", True),
        ("Accountant", True),
        ("Marketing Manager", True),
        ("Product Manager", True),
        ("Solutions Architect", True),
        ("recruiter", True),
        ("evil recruiter", True),
        ("statybos inzinierius", True),
        ("buhalteris", True),
        ("inzinierius", True),
        ("Retail Store Manager", False),
        ("Business Analyst", False),
    ],
)
def test_has_hard_title_mismatch(title: str, expected: bool) -> None:
    assert _has_hard_title_mismatch(title) == expected


def test_normalise_monthly_salary_to_annual():
    from career_job_search.opportunities.normalization import normalise_salary_range
    res = normalise_salary_range("2500 - 3500 €/mėn")
    assert res == (30000.0, 42000.0)


def test_normalise_annual_salary():
    from career_job_search.opportunities.normalization import normalise_salary_range
    res = normalise_salary_range("€40,000 - €50,000 / year")
    assert res == (40000.0, 50000.0)

