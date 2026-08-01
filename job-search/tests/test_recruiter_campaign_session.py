from __future__ import annotations

import argparse
from unittest.mock import patch

from career_job_search.integrations.linkedin import campaign_session
from career_job_search.integrations.linkedin.campaign_runner import (
    target_aware_variant_slug,
    verified_target_company_outreach_allowed,
)
from career_job_search.recruiters.opportunity_targets import (
    OpportunityRecruiterTarget,
)


class FakeAutomation:
    def __init__(self) -> None:
        self.visited: list[str] = []
        self.url = ""

    def goto(self, url: str) -> None:
        self.url = url
        self.visited.append(url)

    def current_url(self) -> str:
        return self.url


def target(
    *,
    company: str = "Hiring Now UAB",
    opportunity_id: str = "opp-hiring-now",
    title: str = "Operations Manager",
) -> OpportunityRecruiterTarget:
    return OpportunityRecruiterTarget(
        opportunity_id=opportunity_id,
        company=company,
        title=title,
        location="Vilnius, Lithuania",
        cv_variant="operations-management",
        role_track="operations leadership",
        fit_score=18,
        status="review",
        live_status="live",
        live_checked_at="2026-07-24T08:00:00+00:00",
        source_url="https://example.com/job",
        priority_reason="fresh_live_match",
    )


def args() -> argparse.Namespace:
    return argparse.Namespace(
        variant_filter=None,
        max_connections_override=None,
        dry_run=True,
    )


def config() -> dict[str, object]:
    return {
        "search": {
            "queries_by_variant": {
                "operations-management": ["generic recruiter query"],
            }
        },
        "web_discovery": {
            "opportunity_targets": {
                "enabled": True,
                "max_companies": 4,
                "min_fit_score": 8,
                "queries_per_company": 1,
            }
        },
    }


def test_company_targets_precede_retries_and_queue_never_exceeds_cap() -> None:
    automation = FakeAutomation()
    raw_cfg = config()

    def harvested(fake: FakeAutomation, **_kwargs: object) -> list[str]:
        if '"Hiring Now UAB"' in fake.url:
            evidence = _kwargs.get("evidence_by_url")
            if isinstance(evidence, dict):
                evidence["https://www.linkedin.com/in/target-one/"] = (
                    "Target One\nOperations recruiter\n"
                    "Current: Talent Partner at Hiring Now UAB"
                )
            return [
                "https://www.linkedin.com/in/target-one/",
                "https://www.linkedin.com/in/target-two/",
            ]
        if '"Second Hiring AB"' in fake.url:
            return ["https://www.linkedin.com/in/target-three/"]
        return [
            "https://www.linkedin.com/in/generic-one/",
            "https://www.linkedin.com/in/generic-two/",
        ]

    retries = [
        ("https://www.linkedin.com/in/target-one/", "operations-management"),
        ("https://www.linkedin.com/in/retry-one/", "operations-management"),
        ("https://www.linkedin.com/in/retry-two/", "operations-management"),
        ("https://www.linkedin.com/in/retry-three/", "operations-management"),
    ]
    with (
        patch.object(
            campaign_session,
            "safe_load_opportunity_targets",
            return_value=(
                [
                    target(),
                    target(
                        company="Second Hiring AB",
                        opportunity_id="opp-second-hiring",
                        title="Area Manager",
                    ),
                ],
                "",
            ),
        ),
        patch.object(
            campaign_session,
            "people_search_url",
            side_effect=lambda query, base_url: f"{base_url}/{query}",
        ),
        patch.object(campaign_session, "dwell_navigation"),
        patch.object(campaign_session, "assert_blocked_automation", return_value=None),
        patch.object(
            campaign_session,
            "harvest_profile_urls",
            side_effect=harvested,
        ),
        patch.object(
            campaign_session,
            "read_retry_connect_queue",
            return_value=retries,
        ),
    ):
        queue = campaign_session.collect_discovery_queue_for_session(
            automation,
            raw_cfg=raw_cfg,
            args=args(),
            scoring_cap=5,
            limits={},
            search=raw_cfg["search"],  # type: ignore[arg-type]
            base_url="https://www.linkedin.com",
            shutdown_browser=lambda: None,
            seen_profiles=set(),
        )

    assert queue is not None
    assert len(queue) == 5
    assert [item[0] for item in queue[:2]] == [
        "https://www.linkedin.com/in/target-one/",
        "https://www.linkedin.com/in/target-three/",
    ]
    assert [item[3] for item in queue[:2]] == [
        "Hiring Now UAB",
        "Second Hiring AB",
    ]
    assert queue[0][4] == "opp-hiring-now"
    assert queue[0][5] == "Operations Manager"
    assert "Current: Talent Partner at Hiring Now UAB" in queue[0][6]
    assert [item[0] for item in queue[2:]] == [
        "https://www.linkedin.com/in/retry-one/",
        "https://www.linkedin.com/in/retry-two/",
        "https://www.linkedin.com/in/retry-three/",
    ]
    assert '"Hiring Now UAB"' in automation.visited[0]
    assert '"Second Hiring AB"' in automation.visited[1]
    assert "generic recruiter query" in automation.visited[2]


def test_generic_search_fills_only_remaining_target_capacity() -> None:
    automation = FakeAutomation()
    raw_cfg = config()

    def harvested(fake: FakeAutomation, **_kwargs: object) -> list[str]:
        if '"Hiring Now UAB"' in fake.url:
            return ["https://www.linkedin.com/in/target-only/"]
        return [
            "https://www.linkedin.com/in/generic-one/",
            "https://www.linkedin.com/in/generic-two/",
        ]

    with (
        patch.object(
            campaign_session,
            "safe_load_opportunity_targets",
            return_value=([target()], ""),
        ),
        patch.object(
            campaign_session,
            "people_search_url",
            side_effect=lambda query, base_url: f"{base_url}/{query}",
        ),
        patch.object(campaign_session, "dwell_navigation"),
        patch.object(campaign_session, "assert_blocked_automation", return_value=None),
        patch.object(
            campaign_session,
            "harvest_profile_urls",
            side_effect=harvested,
        ),
        patch.object(
            campaign_session,
            "read_retry_connect_queue",
            return_value=[],
        ),
    ):
        queue = campaign_session.collect_discovery_queue_for_session(
            automation,
            raw_cfg=raw_cfg,
            args=args(),
            scoring_cap=3,
            limits={},
            search=raw_cfg["search"],  # type: ignore[arg-type]
            base_url="https://www.linkedin.com",
            shutdown_browser=lambda: None,
            seen_profiles=set(),
        )

    assert queue is not None
    assert [item[0] for item in queue] == [
        "https://www.linkedin.com/in/target-only/",
        "https://www.linkedin.com/in/generic-one/",
        "https://www.linkedin.com/in/generic-two/",
    ]
    assert queue[0][3] == "Hiring Now UAB"
    assert queue[1][3] == ""


def test_unpack_queue_item_accepts_legacy_items() -> None:
    assert campaign_session._unpack_queue_item(
        ("https://www.linkedin.com/in/example/", "operations-management")
    ) == (
        "https://www.linkedin.com/in/example/",
        "operations-management",
        "",
        "",
        "",
        "",
        "",
    )


def test_current_company_evidence_excludes_explicit_past_roles() -> None:
    evidence = (
        "Example Person\n"
        "Director of Talent at Current Company\n"
        "Vilnius, Lithuania\n"
        "Past: Talent Partner at Former Company\n"
        "Mutual connections"
    )

    current = campaign_session.current_company_evidence_from_search_result(evidence)

    assert "Current Company" in current
    assert "Former Company" not in current
    assert "Mutual connections" not in current


def test_headline_from_search_result_skips_location_and_relationship_lines() -> None:
    evidence = (
        "Example Person\n"
        "• 2nd\n"
        "Director, Global Talent Acquisition at Vinted\n"
        "Vilnius, Lithuania\n"
        "Current: Vinted\n"
        "3 mutual connections"
    )

    assert campaign_session.headline_from_search_result(evidence) == (
        "Director, Global Talent Acquisition at Vinted"
    )


def test_verified_hiring_company_contact_bypasses_generic_cv_fit_only() -> None:
    result = {
        "recruiter_meta": {
            "recruiter_gate_ok": True,
            "sales_only_no_hiring": False,
        },
        "recommendation": {
            "cv_primary_score": 0,
            "primary_score": 0,
        },
    }
    cfg = {
        "recruiter_matching": {
            "outreach_exclude_terms": ["staffing agency"],
        }
    }

    assert verified_target_company_outreach_allowed(
        result,
        target_company_verified=True,
        current_search_evidence=(
            "Example Person\nCurrent: Country People Partner at Vinted"
        ),
        full_cfg=cfg,
    )


def test_verified_company_override_keeps_current_role_exclusions() -> None:
    result = {
        "recruiter_meta": {
            "recruiter_gate_ok": True,
            "sales_only_no_hiring": False,
        }
    }
    cfg = {
        "recruiter_matching": {
            "outreach_exclude_terms": ["staffing agency"],
        }
    }

    assert not verified_target_company_outreach_allowed(
        result,
        target_company_verified=True,
        current_search_evidence=(
            "Example Person\nCurrent: Recruiter at Universal Staffing Agency"
        ),
        full_cfg=cfg,
    )


def test_verified_target_uses_the_job_cv_variant_for_outreach() -> None:
    recommendation = {"variant_slug": "luxury-retail"}

    assert (
        target_aware_variant_slug(
            recommendation,
            search_variant_slug="business-process-operations",
            verified_target_allowed=True,
        )
        == "business-process-operations"
    )
    assert (
        target_aware_variant_slug(
            recommendation,
            search_variant_slug="business-process-operations",
            verified_target_allowed=False,
        )
        == "luxury-retail"
    )
