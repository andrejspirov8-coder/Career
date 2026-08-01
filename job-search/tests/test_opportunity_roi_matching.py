from __future__ import annotations

from career_job_search.opportunities.matching import match_opportunity
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunitySourceKind,
    OpportunityStatus,
)


def role(
    *,
    title: str = "Operations Manager",
    location: str,
    remote_policy: str = "",
    description: str = (
        "Lead customer operations, service quality, KPI reporting, process "
        "improvement, team leadership, and stakeholder coordination."
    ),
) -> Opportunity:
    return Opportunity(
        source="test",
        source_kind=OpportunitySourceKind.JOB_ALERT,
        source_url="https://example.com/jobs/1",
        title=title,
        company="Example",
        location=location,
        remote_policy=remote_policy,
        description=description,
        live_status="live",
    )


def test_ineligible_location_is_a_hard_review_gate() -> None:
    matched = match_opportunity(
        role(location="New York, United States", remote_policy="onsite")
    )

    assert matched.location_eligibility == "ineligible"
    assert "location_ineligible" in matched.evidence.risk_flags
    assert matched.status == OpportunityStatus.REVIEW


def test_vague_remote_location_requires_verification() -> None:
    matched = match_opportunity(
        role(location="Remote Europe", remote_policy="Remote Europe")
    )

    assert matched.location_eligibility == "verify_remote"
    assert "remote_eligibility_unverified" in matched.evidence.risk_flags
    assert matched.status == OpportunityStatus.REVIEW


def test_remote_eu_and_vilnius_are_confirmed_eligible() -> None:
    remote = match_opportunity(role(location="Remote EU", remote_policy="Remote EU"))
    vilnius = match_opportunity(role(location="Vilnius", remote_policy="hybrid"))

    assert remote.location_eligibility == "eligible_eu_remote"
    assert vilnius.location_eligibility == "eligible_vilnius"
    assert "location_ineligible" not in remote.evidence.risk_flags
    assert "location_ineligible" not in vilnius.evidence.risk_flags


def test_lithuanian_retail_role_routes_to_lithuanian_cv() -> None:
    matched = match_opportunity(
        role(
            title="Parduotuvės vadovas",
            location="Vilniuje",
            description=(
                "Ieškome parduotuvės vadovo. Klientų aptarnavimas, komandos "
                "ugdymas, pardavimų rodikliai, atsargų papildymas, prabangos "
                "prekės ir vizualinis prekių pateikimas."
            ),
        )
    )

    assert matched.match is not None
    assert matched.match.best_variant == "luxury-retail-lt"


def test_engineering_role_remains_blocked_despite_generic_process_words() -> None:
    matched = match_opportunity(
        role(
            title="Senior Software Engineer",
            location="Vilnius",
            description=(
                "Build distributed systems with Python, Kubernetes and "
                "microservices. Work with stakeholders and improve workflows."
            ),
        )
    )

    assert "role_family_mismatch" in matched.evidence.risk_flags
    assert matched.status == OpportunityStatus.REVIEW
