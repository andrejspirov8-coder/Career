from __future__ import annotations

import pytest

from opportunity_eligibility import (
    EligibilityResult,
    LocationEligibility,
    WorkMode,
    classify_location_eligibility,
    is_eligible,
)
from opportunity_models import Opportunity, OpportunitySourceKind


def make_opportunity(
    *,
    location: str = "",
    remote_policy: str = "",
    description: str = "",
) -> Opportunity:
    return Opportunity(
        source="test",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        title="Operations Lead",
        company="Example",
        location=location,
        remote_policy=remote_policy,
        description=description,
    )


@pytest.mark.parametrize(
    ("location", "remote_policy", "expected_mode"),
    [
        ("Vilnius", "onsite", "onsite"),
        ("Vilniaus rajonas", "hybrid", "hybrid"),
        ("Vilniuje", "", "onsite"),
        ("Vilnius region", "on-site", "onsite"),
    ],
)
def test_onsite_or_hybrid_requires_structured_vilnius_location(
    location: str,
    remote_policy: str,
    expected_mode: WorkMode,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(location=location, remote_policy=remote_policy)
    )

    assert result.eligibility == "eligible_vilnius"
    assert result.work_mode == expected_mode
    assert result.reason


def test_description_only_vilnius_does_not_qualify_foreign_onsite_role() -> None:
    result = classify_location_eligibility(
        make_opportunity(
            location="London, United Kingdom",
            remote_policy="onsite",
            description="The role occasionally collaborates with the Vilnius office.",
        )
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "onsite"


@pytest.mark.parametrize(
    "remote_policy",
    ["Not remote", "Remote work is not available"],
)
def test_negated_remote_policy_keeps_structured_location_onsite(
    remote_policy: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(
            location="Kaunas, Lithuania",
            remote_policy=remote_policy,
        )
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "onsite"


def test_no_remote_restrictions_is_generic_remote() -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy="No remote restrictions")
    )

    assert result.eligibility == "verify_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize("allowed_location", ["Lithuania", "Lietuva", "LT"])
def test_remote_with_explicit_lithuania_permission_is_eligible(
    allowed_location: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(
            location="Remote",
            remote_policy=f"Remote from {allowed_location}",
        )
    )

    assert result.eligibility == "eligible_lt_remote"
    assert result.work_mode == "remote"


def test_lt_is_matched_as_a_token_not_inside_an_unrelated_word() -> None:
    result = classify_location_eligibility(
        make_opportunity(location="Remote - Baltic region")
    )

    assert result.eligibility == "verify_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "structured_value",
    [
        "Remote EU",
        "EU remote",
        "Remote within the European Union",
        "Remote across the EEA",
    ],
)
def test_remote_with_explicit_eu_or_eea_permission_is_eligible(
    structured_value: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy=structured_value)
    )

    assert result.eligibility == "eligible_eu_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "structured_value",
    ["Remote Europe", "Europe remote", "Remote EMEA"],
)
def test_plain_europe_or_emea_remote_requires_verification(
    structured_value: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy=structured_value)
    )

    assert result.eligibility == "verify_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "structured_value",
    ["Remote", "Anywhere", "Remote worldwide", "Work from home"],
)
def test_generic_remote_requires_verification(structured_value: str) -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy=structured_value)
    )

    assert result.eligibility == "verify_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    ("location", "remote_policy"),
    [
        ("Remote - United States", "US only"),
        ("Remote - UK", "United Kingdom only"),
        ("Germany", "Remote within Germany"),
        ("Remote EU", "Remote except Lithuania"),
        ("Remote EU", "Lithuania not allowed"),
        ("Remote EU", "Not available to candidates in Lithuania"),
        ("", "Remote other than Lithuania"),
        ("", "Remote apart from Lithuania"),
        ("", "Remote; Lithuania is excluded"),
        ("", "Remote with the exception of Lithuania"),
        ("", "Remote; Lithuania is not eligible"),
    ],
)
def test_remote_restrictions_that_exclude_lithuania_are_ineligible(
    location: str,
    remote_policy: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(location=location, remote_policy=remote_policy)
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    ("location", "remote_policy"),
    [
        ("US Remote", ""),
        ("", "Remote within Bulgaria"),
        ("", "Remote in APAC region"),
    ],
)
def test_foreign_remote_scope_is_ineligible(
    location: str,
    remote_policy: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(location=location, remote_policy=remote_policy)
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


def test_explicit_us_only_restriction_overrides_positive_eu_remote_text() -> None:
    result = classify_location_eligibility(
        make_opportunity(location="Remote EU", remote_policy="US only")
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


def test_remote_except_for_lithuania_is_ineligible() -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy="Remote except for Lithuania")
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


def test_unrelated_country_exclusion_does_not_exclude_lithuania() -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy="Remote worldwide except Germany")
    )

    assert result.eligibility == "verify_remote"
    assert result.work_mode == "remote"


def test_eu_remote_with_lithuania_preference_is_eligible() -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy="Remote in the EU, but Lithuania preferred")
    )

    assert result.eligibility == "eligible_eu_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "remote_policy",
    [
        "Remote Bulgaria only",
        "Remote everywhere but Lithuania",
        "Remote worldwide; candidates must reside in US",
    ],
)
def test_narrow_remote_restriction_overrides_generic_remote_scope(
    remote_policy: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy=remote_policy)
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "foreign_location",
    [
        "Albania",
        "Andorra",
        "Armenia",
        "Azerbaijan",
        "Bosnia and Herzegovina",
        "Bulgaria",
        "Czech Republic",
        "Kazakhstan",
        "Kosovo",
        "Liechtenstein",
        "Monaco",
        "Montenegro",
        "North Macedonia",
        "Russia",
        "San Marino",
        "Türkiye",
        "Vatican City",
    ],
)
def test_remote_restricted_to_common_european_country_is_ineligible(
    foreign_location: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(location=foreign_location, remote_policy="Remote")
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


def test_remote_everywhere_but_not_lithuania_is_ineligible() -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy="Remote everywhere but not Lithuania")
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "remote_policy",
    [
        "Remote worldwide; US residents only",
        "Remote worldwide; UK candidate only",
        "Remote worldwide; Germany workers only",
    ],
)
def test_country_resident_candidate_or_worker_only_is_ineligible(
    remote_policy: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy=remote_policy)
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    "remote_policy",
    [
        "Remote worldwide; candidates must reside in US. EU hours required",
        "Remote within the US; supporting EU clients",
        "US Remote; supporting EU clients",
    ],
)
def test_foreign_remote_restriction_is_bounded_to_its_clause(
    remote_policy: str,
) -> None:
    result = classify_location_eligibility(
        make_opportunity(remote_policy=remote_policy)
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "remote"


def test_foreign_onsite_location_is_ineligible() -> None:
    result = classify_location_eligibility(make_opportunity(location="Berlin, Germany"))

    assert result.eligibility == "ineligible"
    assert result.work_mode == "onsite"


def test_empty_structured_location_is_ineligible_and_unknown() -> None:
    result = classify_location_eligibility(make_opportunity())

    assert result.eligibility == "ineligible"
    assert result.work_mode == "unknown"


def test_description_only_remote_claim_does_not_override_empty_structured_fields() -> (
    None
):
    result = classify_location_eligibility(
        make_opportunity(description="Work remotely from anywhere in the world.")
    )

    assert result.eligibility == "ineligible"
    assert result.work_mode == "unknown"


def test_empty_location_with_structured_remote_policy_requires_verification() -> None:
    result = classify_location_eligibility(make_opportunity(remote_policy="remote"))

    assert result.eligibility == "verify_remote"
    assert result.work_mode == "remote"


@pytest.mark.parametrize(
    ("eligibility", "expected"),
    [
        ("eligible_vilnius", True),
        ("eligible_lt_remote", True),
        ("eligible_eu_remote", True),
        ("verify_remote", False),
        ("ineligible", False),
    ],
)
def test_is_eligible_only_accepts_confirmed_eligibility(
    eligibility: LocationEligibility,
    expected: bool,
) -> None:
    result = EligibilityResult(
        eligibility=eligibility,
        reason="test",
        work_mode="unknown",
    )

    assert is_eligible(result) is expected
