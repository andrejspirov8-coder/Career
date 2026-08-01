from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from career_job_search.opportunities import sources
from career_job_search.opportunities.cvonline_source import (
    discover_cvonline_public_search_source,
)
from career_job_search.opportunities.models import Opportunity, OpportunitySourceKind


def _config(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "opportunities": {
            "sources": {
                "inbox": {"enabled": False},
                "company_watchlist": {"enabled": False},
                "ats": {"enabled": False},
                "cvonline_public_search": {
                    "enabled": True,
                    "queries": ["operations manager"],
                    **block,
                },
            }
        }
    }


def _page(vacancies: list[dict[str, Any]], *, total: int | None = None) -> str:
    payload = {
        "props": {
            "pageProps": {
                "searchResults": {
                    "total": len(vacancies) if total is None else total,
                    "vacancies": vacancies,
                }
            }
        }
    }
    return (
        "<!doctype html><html><body>"
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )


def _vacancy(
    native_id: int,
    *,
    title: str = "Operations Manager",
    company: str = "Example UAB",
    town_id: int | None = 540,
    country_id: int = 92,
    remote_type: str = "ON_SITE",
    expiration: str = "2026-08-31T23:59:59.999+00:00",
    description: str = "<p>Lead operations and improve service.</p>",
    salary_from: int | None = 2500,
    salary_to: int | None = 3500,
) -> dict[str, Any]:
    return {
        "id": native_id,
        "positionTitle": title,
        "employerName": company,
        "townId": town_id,
        "countryId": country_id,
        "remoteWorkType": remote_type,
        "positionContent": description,
        "salaryFrom": salary_from,
        "salaryTo": salary_to,
        "hourlySalary": False,
        "publishDate": "2026-07-20T08:00:00+00:00",
        "renewedDate": "2026-07-23T09:00:00+00:00",
        "expirationDate": expiration,
    }


def test_cvonline_search_keeps_vilnius_and_lithuania_remote_rows_privately() -> None:
    requested: list[tuple[str, int]] = []
    page = _page(
        [
            _vacancy(
                101,
                description=(
                    "<p>Lead operations &amp; improve service.</p>"
                    "<p>Email hiring@example.com or +370 612 34567.</p>"
                    "<p>Kontaktinis asmuo Private Recruiter</p>"
                ),
            ),
            _vacancy(
                102,
                title="Customer Operations Lead",
                remote_type="HYBRID",
            ),
            _vacancy(
                103,
                title="Implementation Manager",
                town_id=None,
                remote_type="FULLY_REMOTE",
                salary_from=3200,
                salary_to=None,
            ),
            _vacancy(
                104,
                title="Kaunas Hybrid Manager",
                town_id=545,
                remote_type="HYBRID",
            ),
            _vacancy(
                105,
                title="Expired Operations Manager",
                expiration="2026-07-23T23:59:59.999+00:00",
            ),
        ]
    )

    def fetch(url: str, *, timeout: int) -> str:
        requested.append((url, timeout))
        return page

    result = discover_cvonline_public_search_source(
        _config({}),
        fetcher=fetch,
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.complete is True
    assert result.note == ""
    assert len(requested) == 1
    query = parse_qs(urlsplit(requested[0][0]).query)
    assert query["keywords[0]"] == ["operations manager"]
    assert query["locations[0]"] == ["Vilnius"]
    assert query["limit"] == ["200"]
    assert query["offset"] == ["0"]
    assert query["fuzzy"] == ["false"]
    assert requested[0][1] == 20

    assert [row.native_source_id for row in result.opportunities] == [
        "101",
        "102",
        "103",
    ]
    onsite, hybrid, remote = result.opportunities
    assert onsite.source == "cvonline"
    assert onsite.source_kind == OpportunitySourceKind.JOB_BOARD
    assert onsite.source_url == "https://www.cvonline.lt/lt/vacancy/101"
    assert onsite.location == "Vilnius"
    assert onsite.remote_policy == "Onsite in Vilnius"
    assert onsite.salary_text == "2,500–3,500 EUR gross/month"
    assert onsite.deadline == "2026-08-31"
    assert onsite.source_updated_at == "2026-07-23T09:00:00+00:00"
    assert onsite.live_status == "live"
    assert onsite.live_check_method == "official_public_search"
    assert onsite.live_check_note == "present_in_current_cvonline_search"
    assert onsite.evidence.source_facts == ["official_search:cvonline"]
    assert onsite.evidence.risk_flags == ["search_summary_only"]
    assert "hiring@example.com" not in onsite.description
    assert "+370 612 34567" not in onsite.description
    assert "Private Recruiter" not in onsite.description
    assert onsite.description.count("[contact removed]") == 2
    assert hybrid.remote_policy == "Hybrid in Vilnius"
    assert remote.location == "Lithuania"
    assert remote.remote_policy == "Remote Lithuania"
    assert remote.salary_text == "3,200 EUR gross/month"


def test_cvonline_search_deduplicates_rows_and_reports_partial_failure() -> None:
    def fetch(url: str, *, timeout: int) -> str:
        del timeout
        query = parse_qs(urlsplit(url).query)["keywords[0]"][0]
        if query == "broken query":
            raise TimeoutError("token=private-value")
        return _page([_vacancy(201)])

    result = discover_cvonline_public_search_source(
        _config(
            {
                "queries": [
                    "operations manager",
                    "customer operations",
                    "broken query",
                ]
            }
        ),
        fetcher=fetch,
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert [row.native_source_id for row in result.opportunities] == ["201"]
    assert result.complete is False
    assert "1 of 3 CV-Online searches failed" in result.note
    assert "private-value" not in result.note


def test_cvonline_search_reports_result_and_query_caps() -> None:
    result = discover_cvonline_public_search_source(
        _config(
            {
                "max_queries": 2,
                "queries": ["one", "two", "three"],
            }
        ),
        fetcher=lambda _url, *, timeout: _page([_vacancy(301)], total=201),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.complete is False
    assert len(result.opportunities) == 1
    assert "2 CV-Online searches exceeded the 200-result cap" in result.note
    assert "query list exceeded its configured cap" in result.note


def test_cvonline_search_fails_safely_when_every_request_fails() -> None:
    def fail(_url: str, *, timeout: int) -> str:
        del timeout
        raise TimeoutError("password=private-value")

    with pytest.raises(
        RuntimeError,
        match="All CV-Online public search requests failed",
    ):
        discover_cvonline_public_search_source(
            _config({"queries": ["one", "two"]}),
            fetcher=fail,
        )


def test_cvonline_search_rejects_an_unbounded_result_limit() -> None:
    with pytest.raises(
        ValueError,
        match="max_results_per_query must be between 1 and 200",
    ):
        discover_cvonline_public_search_source(
            _config({"max_results_per_query": 201}),
            fetcher=lambda _url, *, timeout: "",
        )


def test_cvonline_is_incremental_in_combined_discovery(monkeypatch) -> None:
    row = Opportunity(
        source="cvonline",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="401",
        source_url="https://www.cvonline.lt/lt/vacancy/401",
        title="Operations Manager",
        company="Example UAB",
        location="Vilnius",
        remote_policy="Hybrid in Vilnius",
        description="Lead operations.",
    )
    monkeypatch.setattr(
        sources,
        "discover_cvonline_public_search",
        lambda _config: sources.SourceDiscovery(opportunities=[row]),
    )

    batch = sources.discover_opportunities_with_results(_config({}))

    assert [item.native_source_id for item in batch.opportunities] == ["401"]
    assert batch.opportunities[0].location_eligibility == "eligible_vilnius"
    assert len(batch.source_results) == 1
    assert batch.source_results[0].source == "cvonline"
    assert batch.source_results[0].snapshot_type == "incremental"
    assert batch.source_results[0].status == "success"
    assert batch.source_results[0].complete is True
