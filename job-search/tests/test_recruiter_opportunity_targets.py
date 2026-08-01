from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
)
from career_job_search.opportunities.repository import save_opportunity
from career_job_search.recruiters.dashboard_adapter import build_overview
from career_job_search.recruiters.opportunity_targets import (
    build_opportunity_targets,
    company_name_matches_text,
    opportunity_target_queries,
    opportunity_target_query_rows,
)
from career_job_search.recruiters.web_discovery import discovery_query_plan

NOW = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)


def opportunity(
    *,
    company: str,
    title: str,
    status: OpportunityStatus = OpportunityStatus.REVIEW,
    score: float = 16,
    live_status: str = "live",
    checked_at: datetime | None = NOW,
    eligibility: str = "eligible_vilnius",
    risks: list[str] | None = None,
    variant: str = "operations-management",
) -> Opportunity:
    return Opportunity(
        source="greenhouse",
        source_kind=OpportunitySourceKind.ATS,
        source_url=f"https://example.com/{company.casefold().replace(' ', '-')}/job",
        title=title,
        company=company,
        location="Vilnius, Lithuania",
        location_eligibility=eligibility,
        live_status=live_status,
        live_checked_at=checked_at.isoformat() if checked_at else "",
        live_check_method="ats_feed",
        status=status,
        evidence=OpportunityEvidence(risk_flags=risks or []),
        match=OpportunityMatch(
            best_variant=variant,
            score=score,
            fit_score=score,
            role_track="operations leadership",
        ),
    )


def test_targets_require_relevance_location_and_current_or_advanced_state() -> None:
    fresh = opportunity(company="Fresh Retail", title="Area Manager")
    stale = opportunity(
        company="Stale Retail",
        title="Area Manager",
        checked_at=NOW - timedelta(days=2),
    )
    applied = opportunity(
        company="Applied Company",
        title="Operations Lead",
        status=OpportunityStatus.APPLIED,
        live_status="unknown",
        checked_at=None,
    )
    blocked = opportunity(
        company="Wrong Location",
        title="Store Director",
        risks=["location_ineligible"],
        eligibility="ineligible",
    )

    targets = build_opportunity_targets(
        [stale, blocked, fresh, applied],
        now=NOW,
    )

    assert [target.company for target in targets] == [
        "Applied Company",
        "Fresh Retail",
    ]
    assert targets[0].priority_reason == "human_advanced:applied"
    assert targets[1].priority_reason == "fresh_live_match"


def test_targets_deduplicate_company_and_keep_highest_priority_role() -> None:
    review = opportunity(
        company="Example Group",
        title="Store Manager",
        score=20,
    )
    apply_ready = opportunity(
        company="Example Group",
        title="Regional Operations Lead",
        status=OpportunityStatus.APPLY_READY,
        score=15,
        live_status="unverified",
        checked_at=None,
    )

    targets = build_opportunity_targets([review, apply_ready], now=NOW)

    assert len(targets) == 1
    assert targets[0].title == "Regional Operations Lead"


def test_targets_deduplicate_legal_name_variants() -> None:
    brand_name = opportunity(
        company="Vinted",
        title="Process Design Specialist",
        score=20,
    )
    legal_name = opportunity(
        company="Vinted UAB",
        title="Business Analyst",
        status=OpportunityStatus.APPLY_READY,
        score=15,
        live_status="unverified",
        checked_at=None,
    )

    targets = build_opportunity_targets([brand_name, legal_name], now=NOW)

    assert len(targets) == 1
    assert targets[0].company == "Vinted UAB"
    assert targets[0].title == "Business Analyst"


def test_target_queries_keep_cv_variant_and_company_context() -> None:
    targets = build_opportunity_targets(
        [opportunity(company="Example Group", title="Area Manager")],
        now=NOW,
    )

    queries = opportunity_target_queries(targets)

    assert len(queries) == 2
    assert all(variant == "operations-management" for variant, _ in queries)
    assert all('"Example Group"' in query for _, query in queries)
    assert '"example"' in queries[0][1]
    assert 'recruiter OR "talent acquisition"' in queries[0][1]
    assert '"hiring manager" OR head OR director' in queries[1][1]
    assert '"operations leadership" OR operations OR process' in queries[1][1]


def test_target_query_rows_preserve_job_context() -> None:
    targets = build_opportunity_targets(
        [opportunity(company="Example Group", title="Area Manager")],
        now=NOW,
    )

    rows = opportunity_target_query_rows(targets)

    assert rows[0].target_company == "Example Group"
    assert rows[0].target_opportunity_id == targets[0].opportunity_id
    assert rows[0].target_role_title == "Area Manager"
    assert rows[0].search_intent == "recruiter"
    assert rows[1].search_intent == "hiring_leader"


def test_company_matching_ignores_legal_suffixes_and_handles_brand_separators() -> None:
    assert company_name_matches_text("Vinted UAB", "Talent Acquisition at Vinted")
    assert company_name_matches_text(
        "Citco Group of Companies",
        "Senior Recruiter | Citco",
    )
    assert company_name_matches_text("GR8_TECH", "People Partner at GR8Tech")
    assert not company_name_matches_text("Vinted UAB", "Recruiter at Example Bank")


def test_discovery_query_plan_prioritises_opportunity_companies(tmp_path: Path) -> None:
    db_path = tmp_path / "opportunities.sqlite3"
    save_opportunity(
        opportunity(company="Hiring Now", title="Operations Manager"),
        db_path=db_path,
    )
    cfg = {
        "web_discovery": {
            "opportunity_targets": {
                "enabled": True,
                "max_companies": 4,
                "min_fit_score": 8,
                "queries_per_company": 1,
            },
            "queries_by_variant": {
                "luxury-retail": ["generic recruiter query"],
            },
        }
    }

    queries = discovery_query_plan(cfg, opportunity_db_path=db_path, now=NOW)

    assert queries[0][0] == "operations-management"
    assert '"Hiring Now"' in queries[0][1]
    assert queries[-1] == ("luxury-retail", "generic recruiter query")


def test_recruiter_overview_exposes_current_opportunity_targets(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "opportunities.sqlite3"
    save_opportunity(
        opportunity(
            company="Dashboard Target",
            title="Regional Manager",
            checked_at=datetime.now(UTC),
        ),
        db_path=db_path,
    )

    overview = build_overview(
        action_plan_path=tmp_path / "action-plan.jsonl",
        recruiters_csv_path=tmp_path / "recruiters.csv",
        state_db_path=tmp_path / "recruiter-state.sqlite3",
        run_state_path=tmp_path / "run-state.json",
        persona_stats_path=tmp_path / "persona-stats.json",
        runtime_dir=tmp_path / "runtime",
        action_history_path=tmp_path / "action-history.jsonl",
        opportunity_db_path=db_path,
    )

    assert overview["opportunity_targets"]["count"] == 1
    assert overview["opportunity_targets"]["query_count"] == 2
    assert overview["opportunity_targets"]["companies"][0]["company"] == (
        "Dashboard Target"
    )
