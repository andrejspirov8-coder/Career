from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from opportunity_linkedin import (
    access_block_reason,
    build_search_url,
    canonical_job_url,
    job_id_from_url,
)


def test_build_search_url_contains_location_and_posted_window() -> None:
    url = build_search_url(
        base_url="https://www.linkedin.com/",
        keywords="operations manager",
        location="Vilnius, Lithuania",
        posted_within_hours=72,
        page_number=2,
    )

    parsed = parse_qs(urlsplit(url).query)
    assert url.startswith("https://www.linkedin.com/jobs/search/")
    assert parsed["keywords"] == ["operations manager"]
    assert parsed["location"] == ["Vilnius, Lithuania"]
    assert parsed["f_TPR"] == ["r259200"]
    assert parsed["pageNum"] == ["2"]
    assert parsed["start"] == ["50"]


def test_canonical_job_url_keeps_job_identity_and_drops_tracking() -> None:
    raw = "https://uk.linkedin.com/jobs/view/4567890123/?trackingId=private"

    assert job_id_from_url(raw) == "4567890123"
    assert canonical_job_url(raw) == "https://uk.linkedin.com/jobs/view/4567890123"


@pytest.mark.parametrize(
    ("current_url", "visible_text", "cards", "expected"),
    [
        (
            "https://www.linkedin.com/login",
            "Sign in Join LinkedIn",
            0,
            "linkedin_access_wall:login",
        ),
        (
            "https://www.linkedin.com/jobs/search/",
            "Verify you're human",
            0,
            "linkedin_access_wall:verify you're human",
        ),
        (
            "https://www.linkedin.com/jobs/search/",
            "Sign in Join LinkedIn",
            0,
            "linkedin_login_wall",
        ),
    ],
)
def test_access_wall_is_reported_without_bypass(
    current_url: str,
    visible_text: str,
    cards: int,
    expected: str,
) -> None:
    assert access_block_reason(current_url, visible_text, cards=cards) == expected


def test_public_job_page_without_access_marker_is_not_blocked() -> None:
    assert access_block_reason(
        "https://www.linkedin.com/jobs/search/",
        "Operations Manager Vilnius",
        cards=3,
    ) == ""
