from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from career_job_search.opportunities import sources
from career_job_search.opportunities.cvbankas_source import (
    discover_cvbankas_public_search_source,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
)
from career_job_search.opportunities.workinlithuania_source import (
    discover_workinlithuania_public_search_source,
)
from career_job_search.recruiters.opportunity_targets import (
    build_opportunity_targets,
    opportunity_target_queries,
)

NOW = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)


def _source_config(
    name: str,
    block: dict[str, Any],
) -> dict[str, Any]:
    return {
        "opportunities": {
            "sources": {
                "inbox": {"enabled": False},
                "company_watchlist": {"enabled": False},
                "ats": {"enabled": False},
                name: {"enabled": True, **block},
            }
        }
    }


def _work_config(block: dict[str, Any] | None = None) -> dict[str, Any]:
    return _source_config(
        "workinlithuania_public_search",
        {
            "api_url": "https://jobs.workinlithuania.com/api/job-offers",
            "city_ids": [2, 14],
            "max_pages": 5,
            "max_records": 100,
            "network_timeout_seconds": 20,
            **(block or {}),
        },
    )


def _work_row(
    native_id: int,
    *,
    title: str = "Operations Manager",
    company: str = "Example UAB",
    location: str = "Vilnius",
    salary: str = "3200 - 4200",
    skills: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": native_id,
        "name": title,
        "slug": (
            "https://jobs.workinlithuania.com/job-offers/"
            f"{native_id}-operations-manager"
        ),
        "added_at": "Added 1 day ago",
        "expire_at": "Expires in 7 days",
        "location": location,
        "salary": salary,
        "seniority": "Senior specialist",
        "skills": skills or ["Process improvement", "Team leadership"],
        "company": {
            "name": company,
            "private_contact": "must-not-be-read@example.com",
        },
    }


def _work_page(
    rows: list[dict[str, Any]],
    *,
    current_page: int = 1,
    last_page: int = 1,
    total: int | None = None,
) -> dict[str, Any]:
    return {
        "data": rows,
        "meta": {
            "current_page": current_page,
            "last_page": last_page,
            "per_page": 10,
            "total": len(rows) if total is None else total,
        },
    }


def test_workinlithuania_reads_complete_vilnius_remote_snapshot_privately() -> None:
    requested: list[tuple[str, int]] = []
    pages = {
        1: _work_page(
            [
                _work_row(
                    101,
                    skills=[
                        "Process improvement",
                        "hiring@example.com",
                        "+370 612 34567",
                    ],
                )
            ],
            current_page=1,
            last_page=2,
            total=2,
        ),
        2: _work_page(
            [
                _work_row(
                    102,
                    title="Remote Customer Operations Lead",
                    company="Remote UAB",
                    location="Kaunas, Remote job",
                )
            ],
            current_page=2,
            last_page=2,
            total=2,
        ),
    }

    def fetch(url: str, *, timeout: int) -> dict[str, Any]:
        requested.append((url, timeout))
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        return pages[page]

    result = discover_workinlithuania_public_search_source(
        _work_config(),
        fetcher=fetch,
        now=NOW,
    )

    assert result.complete is True
    assert result.note == ""
    assert len(requested) == 2
    assert all(timeout == 20 for _, timeout in requested)
    first_query = parse_qs(urlsplit(requested[0][0]).query)
    assert first_query["filter[cities]"] == ["2,14"]
    assert first_query["page"] == ["1"]
    assert [row.native_source_id for row in result.opportunities] == ["101", "102"]

    vilnius, remote = result.opportunities
    assert vilnius.source == "workinlithuania"
    assert vilnius.source_kind == OpportunitySourceKind.JOB_BOARD
    assert vilnius.source_url.endswith("/job-offers/101-operations-manager")
    assert vilnius.location == "Vilnius"
    assert vilnius.salary_text == "3200 - 4200 EUR (publisher period not stated)"
    assert vilnius.live_status == "live"
    assert vilnius.live_check_method == "official_public_api"
    assert vilnius.live_check_note == "present_in_current_workinlithuania_search"
    assert vilnius.evidence.source_facts == ["official_api:workinlithuania"]
    assert vilnius.evidence.risk_flags == ["search_summary_only"]
    serialized = str(vilnius.to_json_dict())
    assert "hiring@example.com" not in serialized
    assert "+370 612 34567" not in serialized
    assert "must-not-be-read@example.com" not in serialized
    assert serialized.count("[contact removed]") >= 2

    assert remote.location == "Kaunas, Remote job"
    assert remote.remote_policy == "Remote Lithuania"


def test_workinlithuania_partial_page_failure_never_claims_complete() -> None:
    def fetch(url: str, *, timeout: int) -> dict[str, Any]:
        del timeout
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        if page == 2:
            raise TimeoutError("token=private-value")
        return _work_page(
            [_work_row(201)],
            current_page=1,
            last_page=2,
            total=2,
        )

    result = discover_workinlithuania_public_search_source(
        _work_config(),
        fetcher=fetch,
        now=NOW,
    )

    assert [row.native_source_id for row in result.opportunities] == ["201"]
    assert result.complete is False
    assert "1 Work in Lithuania result page(s) failed" in result.note
    assert "private-value" not in result.note


def test_workinlithuania_caps_and_invalid_rows_make_snapshot_partial() -> None:
    pages = {
        1: _work_page(
            [_work_row(301)],
            current_page=1,
            last_page=3,
            total=3,
        ),
        2: _work_page(
            [
                _work_row(
                    302,
                    location="Kaunas",
                )
            ],
            current_page=2,
            last_page=3,
            total=3,
        ),
    }

    def fetch(url: str, *, timeout: int) -> dict[str, Any]:
        del timeout
        return pages[int(parse_qs(urlsplit(url).query)["page"][0])]

    result = discover_workinlithuania_public_search_source(
        _work_config({"max_pages": 2}),
        fetcher=fetch,
        now=NOW,
    )

    assert [row.native_source_id for row in result.opportunities] == ["301"]
    assert result.complete is False
    assert "exceeded the 2-page cap" in result.note
    assert "invalid or out-of-scope" in result.note


def test_workinlithuania_first_page_failure_is_generic() -> None:
    def fetch(url: str, *, timeout: int) -> dict[str, Any]:
        del url, timeout
        raise TimeoutError("password=private-value")

    with pytest.raises(
        RuntimeError,
        match="Work in Lithuania public search could not be read",
    ) as exc_info:
        discover_workinlithuania_public_search_source(
            _work_config(),
            fetcher=fetch,
            now=NOW,
        )

    assert "private-value" not in str(exc_info.value)


@pytest.mark.parametrize(
    "override",
    [
        {"api_url": "https://example.com/api/job-offers"},
        {"api_url": "http://jobs.workinlithuania.com/api/job-offers"},
        {"city_ids": [1]},
        {"city_ids": []},
        {"max_pages": 11},
        {"max_records": 201},
    ],
)
def test_workinlithuania_rejects_unsafe_or_unbounded_config(
    override: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        discover_workinlithuania_public_search_source(
            _work_config(override),
            fetcher=lambda url, timeout: _work_page([]),
            now=NOW,
        )


def _cvbankas_config(block: dict[str, Any] | None = None) -> dict[str, Any]:
    return _source_config(
        "cvbankas_public_search",
        {
            "base_url": "https://www.cvbankas.lt/",
            "location_ids": [606, 502],
            "max_results_per_query": 50,
            "max_queries": 6,
            "network_timeout_seconds": 20,
            "queries": ["operations manager"],
            **(block or {}),
        },
    )


def _cvbankas_card(
    native_id: int,
    *,
    title: str = "Operations Manager",
    company: str = "Example UAB",
    locations: tuple[str, ...] = ("Vilniuje",),
    timing: str = "prieš 2 d.",
    salary: str = "Nuo 3000",
) -> str:
    city_html = "".join(
        f'<span class="list_city">{location}</span>' for location in locations
    )
    return f"""
    <article id="job_ad_{native_id}">
      <a class="list_a can_visited list_a_has_logo"
         href="https://www.cvbankas.lt/operations-manager-vilniuje/1-{native_id}">
        <img alt="{company}" />
        <h3 class="list_h3">{title}</h3>
        <span class="heading_secondary">
          <span class="dib mt5 mr5">{company}</span>
        </span>
        <span class="salary_c">
          <span class="salary_bl salary_bl_gross">
            <span class="salary_amount">{salary}</span>
            <span class="salary_period">€/mėn.</span>
            <span class="salary_calculation">Neatskaičius mokesčių</span>
          </span>
          <span>Ignored salary calculator</span>
        </span>
        <span class="txt_list_1">{city_html}</span>
        <span class="txt_list_2">{timing}</span>
      </a>
    </article>
    """


def _cvbankas_page(cards: list[str], *, max_page: int = 1) -> str:
    paging = "".join(
        f'<a href="https://www.cvbankas.lt/?page={page}">{page}</a>'
        for page in range(1, max_page + 1)
    )
    return (
        f'<html><body>{"".join(cards)}<ul class="pages_ul">{paging}</ul></body></html>'
    )


def test_cvbankas_uses_exact_bounded_search_and_keeps_public_card_fields() -> None:
    requested: list[tuple[str, int]] = []
    page = _cvbankas_page(
        [
            _cvbankas_card(
                401,
                timing="prieš 2 d. hiring@example.com +370 612 34567",
            ),
            _cvbankas_card(
                402,
                title="Remote Retail Operations Lead",
                company="Remote UAB",
                locations=("Kaune", "Darbas namuose"),
                salary="2500-3500",
            ),
        ]
    )

    def fetch(url: str, *, timeout: int) -> str:
        requested.append((url, timeout))
        return page

    result = discover_cvbankas_public_search_source(
        _cvbankas_config({"queries": ["operations manager", '"retail operations"']}),
        fetcher=fetch,
        now=NOW,
    )

    assert result.complete is True
    assert result.note == ""
    assert len(requested) == 2
    first_query = parse_qs(urlsplit(requested[0][0]).query)
    second_query = parse_qs(urlsplit(requested[1][0]).query)
    assert first_query["keyw"] == ['"operations manager"']
    assert second_query["keyw"] == ['"retail operations"']
    assert first_query["location[]"] == ["606", "502"]
    assert all(timeout == 20 for _, timeout in requested)
    assert [row.native_source_id for row in result.opportunities] == ["401", "402"]

    vilnius, remote = result.opportunities
    assert vilnius.source == "cvbankas"
    assert vilnius.source_kind == OpportunitySourceKind.JOB_BOARD
    assert vilnius.source_url.endswith("/1-401")
    assert vilnius.location == "Vilnius"
    assert vilnius.salary_text == "Nuo 3000 €/mėn. Neatskaičius mokesčių"
    assert vilnius.live_status == "live"
    assert vilnius.live_check_method == "official_public_search"
    assert vilnius.evidence.source_facts == ["official_search:cvbankas"]
    serialized = str(vilnius.to_json_dict())
    assert "hiring@example.com" not in serialized
    assert "+370 612 34567" not in serialized
    assert "[contact removed]" in serialized

    assert remote.location == "Kaune / Remote Lithuania"
    assert remote.remote_policy == "Remote Lithuania"


def test_cvbankas_pagination_failure_and_result_cap_are_visible() -> None:
    cards = [_cvbankas_card(501), _cvbankas_card(502)]
    page = _cvbankas_page(cards, max_page=2)

    result = discover_cvbankas_public_search_source(
        _cvbankas_config({"max_results_per_query": 1}),
        fetcher=lambda url, timeout: page,
        now=NOW,
    )

    assert [row.native_source_id for row in result.opportunities] == ["501"]
    assert result.complete is False
    assert "additional pages" in result.note
    assert "1-result cap" in result.note


def test_cvbankas_partial_failure_retains_success_without_leaking_error() -> None:
    def fetch(url: str, *, timeout: int) -> str:
        del timeout
        query = parse_qs(urlsplit(url).query)["keyw"][0]
        if "broken" in query:
            raise TimeoutError("secret=private-value")
        return _cvbankas_page([])

    result = discover_cvbankas_public_search_source(
        _cvbankas_config({"queries": ["broken query", "operations manager"]}),
        fetcher=fetch,
        now=NOW,
    )

    assert result.opportunities == []
    assert result.complete is False
    assert "1 of 2 CVBankas searches failed" in result.note
    assert "private-value" not in result.note


def test_cvbankas_all_failures_raise_generic_error() -> None:
    def fetch(url: str, *, timeout: int) -> str:
        del url, timeout
        raise TimeoutError("api_key=private-value")

    with pytest.raises(
        RuntimeError,
        match="All CVBankas public search requests failed",
    ) as exc_info:
        discover_cvbankas_public_search_source(
            _cvbankas_config(),
            fetcher=fetch,
            now=NOW,
        )

    assert "private-value" not in str(exc_info.value)


def test_cvbankas_invalid_or_out_of_scope_cards_make_result_partial() -> None:
    page = _cvbankas_page(
        [
            _cvbankas_card(
                601,
                locations=("Kaune",),
            ),
            """
            <a class="list_a" href="https://example.com/job/1-602">
              <h3 class="list_h3">Operations Manager</h3>
              <span class="dib mt5 mr5">Example UAB</span>
              <span class="list_city">Vilniuje</span>
            </a>
            """,
        ]
    )
    result = discover_cvbankas_public_search_source(
        _cvbankas_config(),
        fetcher=lambda url, timeout: page,
        now=NOW,
    )

    assert result.opportunities == []
    assert result.complete is False
    assert "2 invalid or out-of-scope CVBankas card(s)" in result.note


@pytest.mark.parametrize(
    "override",
    [
        {"base_url": "https://example.com/"},
        {"base_url": "http://www.cvbankas.lt/"},
        {"location_ids": [1]},
        {"location_ids": []},
        {"max_results_per_query": 51},
        {"max_queries": 7},
        {"queries": []},
        {"queries": ['operations "manager"']},
    ],
)
def test_cvbankas_rejects_unsafe_or_unbounded_config(
    override: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        discover_cvbankas_public_search_source(
            _cvbankas_config(override),
            fetcher=lambda url, timeout: _cvbankas_page([]),
            now=NOW,
        )


def test_lithuania_board_source_results_use_safe_reconciliation_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_row = Opportunity(
        source="workinlithuania",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="701",
        source_url=(
            "https://jobs.workinlithuania.com/job-offers/701-operations-manager"
        ),
        title="Operations Manager",
        company="Work Company",
        location="Vilnius",
    )
    cvbankas_row = Opportunity(
        source="cvbankas",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="702",
        source_url="https://www.cvbankas.lt/operations-manager/1-702",
        title="Operations Manager",
        company="Bankas Company",
        location="Vilnius",
    )
    config = _work_config()
    config["opportunities"]["sources"]["cvbankas_public_search"] = {"enabled": True}
    monkeypatch.setattr(
        sources,
        "discover_workinlithuania_public_search",
        lambda config: sources.SourceDiscovery([work_row]),
    )
    monkeypatch.setattr(
        sources,
        "discover_cvbankas_public_search",
        lambda config: sources.SourceDiscovery([cvbankas_row]),
    )

    batch = sources.discover_opportunities_with_results(config)

    assert [result.source for result in batch.source_results] == [
        "cvbankas",
        "workinlithuania",
    ]
    assert [result.snapshot_type for result in batch.source_results] == [
        "incremental",
        "snapshot",
    ]
    assert [result.complete for result in batch.source_results] == [True, True]


def test_workinlithuania_match_seeds_read_only_recruiter_targets() -> None:
    result = discover_workinlithuania_public_search_source(
        _work_config(),
        fetcher=lambda url, timeout: _work_page([_work_row(801)]),
        now=NOW,
    )
    row = result.opportunities[0]
    row.location_eligibility = "eligible_vilnius"
    row.status = OpportunityStatus.REVIEW
    row.match = OpportunityMatch(
        best_variant="operations-management",
        score=18,
        fit_score=18,
        role_track="operations leadership",
    )

    targets = build_opportunity_targets([row], now=NOW)
    queries = opportunity_target_queries(targets)

    assert [target.company for target in targets] == ["Example UAB"]
    assert len(queries) == 2
    assert all('"Example UAB"' in query for _, query in queries)
