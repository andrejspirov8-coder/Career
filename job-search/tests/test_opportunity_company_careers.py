from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from career_job_search.opportunities import sources
from career_job_search.opportunities.company_careers_source import (
    discover_official_company_careers_source,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
)
from career_job_search.recruiters.opportunity_targets import (
    build_opportunity_targets,
    opportunity_target_queries,
)

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)


def _config(
    provider: str,
    *,
    block: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    listing_urls = {
        "vinted": "https://careers.vinted.com/jobs",
        "wolt": "https://careers.wolt.com/en/jobs",
        "bolt": "https://bolt.eu/en/careers/positions/",
    }
    company = provider.title()
    company_config = {
        "provider": provider,
        "company": company,
        "listing_url": listing_urls[provider],
    }
    config = {
        "opportunities": {
            "sources": {
                "inbox": {"enabled": False},
                "company_watchlist": {"enabled": False},
                "ats": {"enabled": False},
                "official_company_careers": {
                    "enabled": True,
                    "max_rows_per_company": 400,
                    "companies": [company_config],
                    **(block or {}),
                },
            }
        }
    }
    return config, company_config


def _next_data_page(jobs: list[dict[str, Any]]) -> str:
    payload = {
        "props": {
            "pageProps": {
                "jobs": {
                    "dataMap": {
                        "vinteden": {
                            "jobs": jobs,
                        }
                    }
                }
            }
        }
    }
    return (
        "<html><body>"
        '<script type="application/json" id="__NEXT_DATA__">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )


def _rsc_page(*rows: dict[str, Any]) -> str:
    stream = "".join(
        json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows
    )
    payload = json.dumps([1, stream], ensure_ascii=False)
    return f"<html><body><script>self.__next_f.push({payload})</script></body></html>"


def _vinted_group() -> dict[str, Any]:
    return {
        "id": 101,
        "title": "Operations Manager",
        "location": {"name": "Multiple locations, Lithuania"},
        "company_name": "Vinted",
        "content": "<p>Parent description.</p>",
        "updated_at": "2026-07-22T09:30:00+00:00",
        "items": [
            {
                "id": 101,
                "title": "Operations Manager",
                "city": {"name": "Vilnius"},
                "country": {"name": "Lithuania"},
                "content": (
                    "<p>Lead a hybrid operations team.</p>"
                    "<p>Email hiring@example.com or call +44 20 1234 5678.</p>"
                    "<p>Contact person Private Recruiter</p>"
                ),
                "departments": [{"name": "Business & Commercial"}],
                "updated_at": "2026-07-23T10:00:00+00:00",
                "application_deadline": "2026-08-15T23:59:59+00:00",
            },
            {
                "id": 102,
                "title": "Operations Manager",
                "city": {"name": "Kaunas"},
                "country": {"name": "Lithuania"},
                "content": "<p>Kaunas-only role.</p>",
            },
        ],
    }


def test_vinted_flattens_grouped_jobs_and_keeps_only_vilnius_privately() -> None:
    config, company_config = _config("vinted")
    page = _next_data_page(
        [
            _vinted_group(),
            {
                "id": 103,
                "title": "Berlin Operations Manager",
                "city": {"name": "Berlin"},
                "country": {"name": "Germany"},
                "content": "<p>Berlin role.</p>",
            },
        ]
    )
    requested: list[tuple[str, int]] = []

    def fetch(url: str, *, timeout: int) -> str:
        requested.append((url, timeout))
        return page

    result = discover_official_company_careers_source(
        config,
        company_config,
        fetcher=fetch,
        now=NOW,
    )

    assert requested == [("https://careers.vinted.com/jobs", 30)]
    assert result.complete is True
    assert result.note == ""
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.source == "company_careers:vinted"
    assert row.source_kind == OpportunitySourceKind.COMPANY_SITE
    assert row.native_source_id == "101"
    assert row.source_url == "https://careers.vinted.com/jobs/j/101"
    assert row.title == "Operations Manager"
    assert row.company == "Vinted"
    assert row.location == "Vilnius, Lithuania"
    assert row.remote_policy == "Hybrid in Vilnius"
    assert row.deadline == "2026-08-15"
    assert row.source_updated_at == "2026-07-23T10:00:00+00:00"
    assert row.live_status == "live"
    assert row.live_check_method == "official_public_career_search"
    assert row.evidence.source_facts[0] == "official_careers:vinted"
    assert "hiring@example.com" not in row.description
    assert "+44 20 1234 5678" not in row.description
    assert "Private Recruiter" not in row.description
    assert row.description.count("[contact removed]") == 2


def test_wolt_imports_vilnius_summary_and_lithuania_salary() -> None:
    config, company_config = _config("wolt")
    page = _rsc_page(
        {
            "id": 201,
            "internalId": 2001,
            "boardId": "en",
            "title": "Merchant Operations Manager",
            "employmentType": "Full-time",
            "departments": [{"name": "Sales & Merchant Operations"}],
            "offices": [{"name": "Vilnius, Lithuania"}],
            "payRanges": [
                {
                    "minAmount": 3800,
                    "maxAmount": 5700,
                    "currency": "EUR",
                    "title": "Lithuania Pay Range:",
                }
            ],
        },
        {
            "id": 202,
            "internalId": 2002,
            "boardId": "en",
            "title": "Warsaw Manager",
            "employmentType": "Full-time",
            "departments": [{"name": "Operations"}],
            "offices": [{"name": "Warsaw, Poland"}],
            "payRanges": [],
        },
    )

    result = discover_official_company_careers_source(
        config,
        company_config,
        fetcher=lambda _url, *, timeout: page,
        now=NOW,
    )

    assert result.complete is True
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.source == "company_careers:wolt"
    assert row.native_source_id == "201"
    assert row.source_url == "https://careers.wolt.com/en/jobs/1/201"
    assert row.location == "Vilnius, Lithuania"
    assert row.salary_text == "3,800–5,700 EUR · Lithuania Pay Range"
    assert "Sales & Merchant Operations" in row.description


def test_bolt_imports_vilnius_description_salary_and_posted_date_privately() -> None:
    config, company_config = _config("bolt")
    page = _rsc_page(
        {
            "id": "570efdb1-3454-4fc9-8906-9647615914ed",
            "header": {
                "roleTitle": "Strategic Operations Manager",
                "parentTeamTitle": "Local Operations",
                "locations": [
                    {
                        "city": "Vilnius",
                        "country": "Lithuania",
                        "countryCode": "lt",
                    }
                ],
            },
            "body": {
                "description": (
                    "Hybrid role. Monthly gross salary ranges from "
                    "3,400 € to 4,500 €. Email recruiter@example.com. "
                    "If you have any questions contact Private Recruiter."
                ),
                "jobPostedDate": "$D2026-07-14T00:00:00.000Z",
            },
        },
        {
            "id": "d7b10892-c4a9-4638-ace0-e9f1a73bd34e",
            "header": {
                "roleTitle": "Kaunas Operations Manager",
                "parentTeamTitle": "Operations",
                "locations": [{"city": "Kaunas", "country": "Lithuania"}],
            },
            "body": {
                "description": "Kaunas role.",
                "jobPostedDate": "$D2026-07-10T00:00:00.000Z",
            },
        },
    )

    result = discover_official_company_careers_source(
        config,
        company_config,
        fetcher=lambda _url, *, timeout: page,
        now=NOW,
    )

    assert result.complete is True
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.source == "company_careers:bolt"
    assert row.title == "Strategic Operations Manager"
    assert row.remote_policy == "Hybrid in Vilnius"
    assert row.salary_text == "3,400–4,500 EUR gross/month"
    assert row.source_updated_at == "2026-07-14T00:00:00.000Z"
    assert "recruiter@example.com" not in row.description
    assert "Private Recruiter" not in row.description


def test_company_source_marks_a_capped_page_incomplete() -> None:
    config, company_config = _config(
        "vinted",
        block={"max_rows_per_company": 1},
    )
    group = _vinted_group()
    group["items"][1]["city"] = {"name": "Vilnius"}

    result = discover_official_company_careers_source(
        config,
        company_config,
        fetcher=lambda _url, *, timeout: _next_data_page([group]),
        now=NOW,
    )

    assert result.complete is False
    assert len(result.opportunities) == 1
    assert "exceeded the 1-job processing cap" in result.note


def test_company_source_fails_safely_when_public_job_data_disappears() -> None:
    config, company_config = _config("wolt")

    with pytest.raises(
        ValueError,
        match="returned no parseable jobs",
    ):
        discover_official_company_careers_source(
            config,
            company_config,
            fetcher=lambda _url, *, timeout: _rsc_page({"other": "data"}),
        )


def test_company_source_rejects_non_official_hosts() -> None:
    config, company_config = _config("bolt")
    company_config["listing_url"] = "https://example.com/en/careers/positions/"

    with pytest.raises(ValueError, match="official HTTPS host"):
        discover_official_company_careers_source(
            config,
            company_config,
            fetcher=lambda _url, *, timeout: "",
        )


def test_company_sources_are_independent_complete_snapshots(monkeypatch) -> None:
    config, _ = _config("vinted")
    config["opportunities"]["sources"]["official_company_careers"]["companies"] = [
        {
            "provider": "vinted",
            "company": "Vinted",
            "listing_url": "https://careers.vinted.com/jobs",
        },
        {
            "provider": "wolt",
            "company": "Wolt",
            "listing_url": "https://careers.wolt.com/en/jobs",
        },
    ]

    def discover(
        _config: dict[str, Any],
        company_config: dict[str, Any],
    ) -> sources.SourceDiscovery:
        provider = company_config["provider"]
        if provider == "wolt":
            raise TimeoutError("token=private-value")
        row = Opportunity(
            source=f"company_careers:{provider}",
            source_kind=OpportunitySourceKind.COMPANY_SITE,
            native_source_id="301",
            source_url="https://careers.vinted.com/jobs/j/301",
            title="Operations Manager",
            company="Vinted",
            location="Vilnius, Lithuania",
            description="Lead operations.",
        )
        return sources.SourceDiscovery(opportunities=[row])

    monkeypatch.setattr(sources, "discover_official_company_careers", discover)

    batch = sources.discover_opportunities_with_results(config)

    assert [row.title for row in batch.opportunities] == ["Operations Manager"]
    assert [result.source for result in batch.source_results] == [
        "company_careers:vinted",
        "company_careers:wolt",
    ]
    assert [result.snapshot_type for result in batch.source_results] == [
        "snapshot",
        "snapshot",
    ]
    assert [result.status for result in batch.source_results] == [
        "success",
        "failed",
    ]
    assert "private-value" not in batch.source_results[1].error
    assert batch.partial is True


def test_company_career_match_seeds_company_specific_recruiter_queries() -> None:
    opportunity = Opportunity(
        source="company_careers:bolt",
        source_kind=OpportunitySourceKind.COMPANY_SITE,
        native_source_id="401",
        source_url="https://bolt.eu/en/careers/positions/401/",
        title="Strategic Operations Manager",
        company="Bolt",
        location="Vilnius, Lithuania",
        location_eligibility="eligible_vilnius",
        live_status="live",
        live_checked_at=NOW.isoformat(),
        live_check_method="official_public_career_search",
        status=OpportunityStatus.REVIEW,
        evidence=OpportunityEvidence(),
        match=OpportunityMatch(
            best_variant="operations-management",
            score=18,
            fit_score=18,
            role_track="operations leadership",
        ),
    )

    targets = build_opportunity_targets([opportunity], now=NOW)
    queries = opportunity_target_queries(targets)

    assert [target.company for target in targets] == ["Bolt"]
    assert len(queries) == 2
    assert all('"Bolt"' in query for _, query in queries)
    assert all(variant == "operations-management" for variant, _ in queries)
