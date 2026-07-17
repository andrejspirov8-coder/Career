from __future__ import annotations

from typing import Any

import opportunity_sources as sources
from opportunity_models import Opportunity, OpportunitySourceKind, OpportunityStatus


def test_discovery_reports_partial_ats_failure_without_hiding_good_source(
    monkeypatch,
) -> None:
    def fake_fetch(url: str, *, timeout: int) -> Any:
        if "broken" in url:
            raise TimeoutError("token=secret source timed out")
        return {
            "jobs": [
                {
                    "id": "vilnius-1",
                    "title": "Operations Lead",
                    "absolute_url": "https://example.com/jobs/vilnius-1",
                    "location": {"name": "Vilnius"},
                    "content": "Lead customer operations in Vilnius.",
                }
            ]
        }

    monkeypatch.setattr(sources, "fetch_json", fake_fetch)
    config = {
        "opportunities": {
            "sources": {
                "inbox": {"enabled": False},
                "company_watchlist": {"enabled": False},
                "ats": {
                    "enabled": True,
                    "providers": [
                        {
                            "provider": "greenhouse",
                            "company": "Good",
                            "board_token": "good",
                        },
                        {
                            "provider": "greenhouse",
                            "company": "Broken",
                            "board_token": "broken",
                        },
                    ],
                },
            }
        }
    }

    batch = sources.discover_opportunities_with_results(config)

    assert [row.title for row in batch.opportunities] == ["Operations Lead"]
    assert [result.status for result in batch.source_results] == [
        "success",
        "failed",
    ]
    assert batch.partial is True
    assert "secret" not in batch.source_results[1].error
    assert batch.source_results[1].snapshot_type == "snapshot"
    assert batch.source_results[1].complete is False


def test_ats_cap_is_applied_after_location_filtering(monkeypatch) -> None:
    monkeypatch.setattr(
        sources,
        "fetch_json",
        lambda _url, *, timeout: {
            "jobs": [
                {
                    "id": "us-1",
                    "title": "Operations Lead",
                    "absolute_url": "https://example.com/jobs/us-1",
                    "location": {"name": "New York, United States"},
                    "content": "Onsite role.",
                },
                {
                    "id": "vilnius-1",
                    "title": "Operations Manager",
                    "absolute_url": "https://example.com/jobs/vilnius-1",
                    "location": {"name": "Vilnius"},
                    "content": "Lead customer operations.",
                },
                {
                    "id": "eu-1",
                    "title": "Process Lead",
                    "absolute_url": "https://example.com/jobs/eu-1",
                    "location": {"name": "Remote EU"},
                    "content": "Improve business processes.",
                },
            ]
        },
    )
    config = {
        "opportunities": {
            "sources": {
                "inbox": {"enabled": False},
                "company_watchlist": {"enabled": False},
                "ats": {
                    "enabled": True,
                    "providers": [
                        {
                            "provider": "greenhouse",
                            "company": "Example",
                            "board_token": "example",
                            "max_posts": 1,
                        }
                    ],
                },
            }
        }
    }

    batch = sources.discover_opportunities_with_results(config)

    assert [row.title for row in batch.opportunities] == ["Operations Manager"]
    assert batch.opportunities[0].location_eligibility == "eligible_vilnius"
    assert batch.source_results[0].item_count == 1


def test_legacy_discover_api_returns_only_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        sources,
        "discover_opportunities_with_results",
        lambda _config: sources.DiscoveryBatch(opportunities=[], source_results=[]),
    )

    assert sources.discover_opportunities({}) == []


def test_enabled_linkedin_source_is_collected(monkeypatch) -> None:
    row = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="linkedin-123",
        source_url="https://www.linkedin.com/jobs/view/123",
        title="Customer Operations Manager",
        company="Example UAB",
        location="Vilnius",
        description="Customer operations and process improvement.",
    )
    monkeypatch.setattr(sources, "discover_linkedin_jobs", lambda _config: [row])

    batch = sources.discover_opportunities_with_results(
        {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": False},
                    "company_watchlist": {"enabled": False},
                    "ats": {"enabled": False},
                    "linkedin": {"enabled": True},
                }
            }
        }
    )

    assert [item.title for item in batch.opportunities] == [
        "Customer Operations Manager"
    ]
    assert batch.source_results[0].source == "linkedin"
    assert batch.source_results[0].status == "success"
    assert batch.source_results[0].item_count == 1
    assert batch.opportunities[0].location_eligibility == "eligible_vilnius"


def test_connected_chrome_mode_delegates_discovery_to_browser_automation(
    monkeypatch,
) -> None:
    def should_not_open_local_profile(_config: dict[str, object]) -> list[object]:
        raise AssertionError("connected Chrome mode must not launch a local profile")

    monkeypatch.setattr(sources, "discover_linkedin_jobs", should_not_open_local_profile)

    batch = sources.discover_opportunities_with_results(
        {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": False},
                    "company_watchlist": {"enabled": False},
                    "ats": {"enabled": False},
                    "linkedin": {"enabled": True, "mode": "connected_chrome"},
                }
            }
        }
    )

    assert batch.opportunities == []
    assert batch.source_results == []


def test_company_watchlist_is_monitor_only_not_a_job_snapshot() -> None:
    batch = sources.discover_opportunities_with_results(
        {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": False},
                    "company_watchlist": {
                        "enabled": True,
                        "companies": [
                            {
                                "name": "Example Company",
                                "careers_url": "https://example.com/careers",
                            }
                        ],
                    },
                    "ats": {"enabled": False},
                }
            }
        }
    )

    assert len(batch.opportunities) == 1
    assert batch.opportunities[0].status == OpportunityStatus.SKIPPED
    assert batch.opportunities[0].next_action == "wait"
    assert batch.source_results[0].status == "monitor_only"
    assert batch.source_results[0].snapshot_type == "snapshot"
    assert batch.partial is False
