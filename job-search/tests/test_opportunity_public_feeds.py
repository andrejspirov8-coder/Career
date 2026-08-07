from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from career_job_search.opportunities import sources


def _source_config(name: str, block: dict[str, object]) -> dict[str, object]:
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


def test_cvmarket_official_rss_imports_only_configured_vilnius_rows(
    monkeypatch,
) -> None:
    rss = """\
<rss version="2.0">
  <channel>
    <lastBuildDate>Thu, 23 Jul 2026 22:10:18 +0300</lastBuildDate>
    <item>
      <link>https://www.cvmarket.lt/process-design-specialist-escalation-processes-vilnius-vinted-uab-2280050</link>
      <pubDate>Thu, 23 Jul 2026 04:41:01 +0300</pubDate>
      <title>Process Design Specialist (Escalation Processes)</title>
    </item>
    <item>
      <link>https://www.cvmarket.lt/operations-manager-kaunas-example-uab-2280051</link>
      <pubDate>Thu, 23 Jul 2026 04:42:01 +0300</pubDate>
      <title>Operations Manager</title>
    </item>
  </channel>
</rss>
"""
    monkeypatch.setattr(
        sources.providers,
        "fetch_text",
        lambda _url, *, timeout: rss,
    )
    config = _source_config(
        "cvmarket_rss",
        {
            "locations": ["Vilnius"],
            "max_feed_age_hours": 48,
        },
    )

    result = sources.discover_cvmarket_rss(
        config,
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.status is None
    assert result.complete is True
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.native_source_id == "2280050"
    assert row.title == "Process Design Specialist (Escalation Processes)"
    assert row.company == "Vinted UAB"
    assert row.location == "Vilnius"
    assert row.live_status == "unverified"
    assert row.live_check_method == "official_rss"
    assert "rss_summary_only" in row.evidence.risk_flags


def test_cvmarket_feed_age_is_reported_as_stale(monkeypatch) -> None:
    rss = """\
<rss version="2.0">
  <channel>
    <lastBuildDate>Mon, 20 Jul 2026 08:00:00 +0000</lastBuildDate>
  </channel>
</rss>
"""
    monkeypatch.setattr(
        sources.providers,
        "fetch_text",
        lambda _url, *, timeout: rss,
    )

    result = sources.discover_cvmarket_rss(
        _source_config(
            "cvmarket_rss",
            {"locations": ["Vilnius"], "max_feed_age_hours": 48},
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.status == "stale"
    assert "96 hours old" in result.note


def test_cvmarket_is_an_incremental_source_in_combined_discovery(monkeypatch) -> None:
    row = sources.Opportunity(
        source="cvmarket",
        source_kind=sources.OpportunitySourceKind.JOB_BOARD,
        source_url="https://www.cvmarket.lt/process-lead-vilnius-example-uab-1",
        title="Process Lead",
        company="Example UAB",
        location="Vilnius",
    )
    monkeypatch.setattr(
        sources,
        "discover_cvmarket_rss",
        lambda _config: sources.SourceDiscovery(opportunities=[row]),
    )

    batch = sources.discover_opportunities_with_results(
        _source_config("cvmarket_rss", {})
    )

    assert batch.source_results[0].source == "cvmarket"
    assert batch.source_results[0].snapshot_type == "incremental"
    assert batch.source_results[0].status == "success"


def test_uzt_open_data_requests_no_contact_columns_and_redacts_description(
    monkeypatch,
) -> None:
    seen_query: dict[str, list[str]] = {}

    def fake_fetch(url: str, *, timeout: int) -> dict[str, object]:
        seen_query.update(parse_qs(urlsplit(url).query))
        return {
            "_data": [
                {
                    "_id": "public-row-1",
                    "darbo_vietos_id": "DV-01-996740308",
                    "ikelimo_data": "2026-07-23",
                    "prelim_darbo_uzmokestis": 2500,
                    "maks_darbo_uzmokestis": 3000,
                    "valiuta": "EUR",
                    "uzmokescio_komentaras_lt": "",
                    "profesijos_pareigybes_pav": "Procesų valdymo vadovas",
                    "kontrakto_tipas": "Neterminuota",
                    "darbo_aprasymas_lt": (
                        "Tobulinti veiklos procesus. "
                        "CV siųskite private.person@example.lt. "
                        "Skambinkite +370 612 34567."
                    ),
                    "galioja_iki": "2026-08-10",
                    "darbo_vietu_skaicius": 1,
                    "darbo_vietos_sav_pav": "Vilniaus miesto sav.",
                    "darbdavys": "LTG, AB",
                    "reik_darbo_patirtis": 3,
                    "reik_kompetencijos_lt": "Procesų analizė",
                    "reik_gebejimai": "Komandos valdymas",
                    "reik_issilavinimo_pav": "Aukštasis",
                }
            ]
        }

    monkeypatch.setattr(sources.providers, "fetch_json", fake_fetch)
    result = sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {
                "municipality": "Vilniaus miesto sav.",
                "max_records": 500,
                "max_feed_age_days": 3,
            },
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    selected_fields = set(seen_query["_select"][0].split(","))
    assert {
        "darbdavio_kontaktinis_asmuo",
        "darbdavio_tel_nr",
        "darbdavio_mob_nr",
        "darbdavio_el_pastas",
    }.isdisjoint(selected_fields)
    assert seen_query["ar_aktuali_siandien"] == ['"1"']
    assert seen_query["darbo_vietos_sav_pav"] == ['"Vilniaus miesto sav."']
    assert seen_query["galioja_iki._ge"] == ['"2026-07-24"']
    assert result.status is None
    assert result.complete is True
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.source == "uzt_open_data"
    assert row.native_source_id == "DV-01-996740308"
    assert row.source_url.endswith("/skelbimas/DV-01-996740308")
    assert row.title == "Procesų valdymo vadovas"
    assert row.company == "LTG, AB"
    assert row.location == "Vilnius"
    assert row.salary_text == "2,500–3,000 EUR"
    assert row.deadline == "2026-08-10"
    assert "private.person" not in row.description
    assert "612 34567" not in row.description
    assert "contact instructions removed" in row.description
    assert "license:CC-BY-4.0" in row.evidence.source_facts


def test_uzt_old_publication_date_marks_feed_and_rows_stale(monkeypatch) -> None:
    monkeypatch.setattr(
        sources.providers,
        "fetch_json",
        lambda _url, *, timeout: {
            "_data": [
                {
                    "darbo_vietos_id": "DV-01-996740308",
                    "ikelimo_data": "2026-07-08",
                    "profesijos_pareigybes_pav": "Procesų valdymo vadovas",
                    "darbdavys": "LTG, AB",
                }
            ]
        },
    )

    result = sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {
                "max_records": 500,
                "max_feed_age_days": 3,
                "live_fallback_enabled": False,
            },
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.status == "stale"
    assert "392 hours old" in result.note
    assert result.opportunities[0].live_check_note == "source_feed_is_stale"
    assert "stale_source" in result.opportunities[0].evidence.risk_flags


def test_uzt_stale_open_data_uses_current_official_search_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sources.providers,
        "fetch_json",
        lambda _url, *, timeout: {
            "_data": [
                {
                    "darbo_vietos_id": "DV-01-OLD",
                    "ikelimo_data": "2026-07-08",
                    "profesijos_pareigybes_pav": "Old vacancy",
                    "darbdavys": "Old employer",
                }
            ]
        },
    )
    seen_urls: list[str] = []
    current_search = """\
<html>
  <head>
    <link rel="next" href="/laisvos-darbo-vietos/436/results/p100?n=100">
  </head>
  <body>
    <a class="list__item"
       href="/laisvos-darbo-vietos/436/skelbimas/DV-01-996740623?private=ignored">
      <div class="title"><strong>Procesų valdymo vadovas</strong></div>
      <div class="company">LTG, AB</div>
      <div class="salary">€2500.00 / per mėn.</div>
      <div class="district">Vilniaus miesto sav.</div>
      <div class="location">Vilnius</div>
      <div class="created-date">Įkelta: 2026-07-23</div>
      <div class="expiry-date">Galioja: 2026-08-10</div>
      <div class="contact">private.person@example.lt +370 612 34567</div>
    </a>
    <a class="list__item"
       href="https://evil.example/laisvos-darbo-vietos/436/skelbimas/DV-EVIL">
      <div class="title">External vacancy</div>
      <div class="company">External employer</div>
      <div class="district">Vilniaus miesto sav.</div>
      <div class="created-date">Įkelta: 2026-07-24</div>
    </a>
  </body>
</html>
"""

    def fake_text_fetch(url: str, *, timeout: int) -> str:
        seen_urls.append(url)
        return current_search

    monkeypatch.setattr(sources.providers, "fetch_text", fake_text_fetch)
    result = sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {
                "max_records": 500,
                "max_feed_age_days": 3,
                "live_fallback_enabled": True,
                "live_fallback_municipality_id": 461,
                "live_fallback_max_records": 100,
            },
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert len(seen_urls) == 1
    live_query = parse_qs(urlsplit(seen_urls[0]).query)
    assert live_query == {"n": ["100"], "o": ["ctime"], "m[]": ["461"]}
    assert result.status is None
    assert result.complete is False
    assert "Current official public-search fallback supplied 1" in result.note
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.source == "uzt_open_data"
    assert row.native_source_id == "DV-01-996740623"
    assert row.source_url == (
        "https://uzt.lt/laisvos-darbo-vietos/436/skelbimas/DV-01-996740623"
    )
    assert row.title == "Procesų valdymo vadovas"
    assert row.company == "LTG, AB"
    assert row.location == "Vilnius"
    assert row.salary_text == "€2500.00 / per mėn."
    assert row.deadline == "2026-08-10"
    assert row.source_updated_at == "2026-07-23"
    assert row.live_status == "live"
    assert row.live_check_method == "official_public_search"
    assert "search_summary_only" in row.evidence.risk_flags
    serialized = row.model_dump_json()
    assert "private.person" not in serialized
    assert "612 34567" not in serialized
    assert "evil.example" not in serialized


def test_uzt_open_data_failure_uses_current_official_search_fallback(
    monkeypatch,
) -> None:
    def failed_open_data(_url: str, *, timeout: int) -> object:
        del timeout
        raise OSError("HTTP 500")

    monkeypatch.setattr(sources.providers, "fetch_json", failed_open_data)
    monkeypatch.setattr(
        sources.providers,
        "fetch_text",
        lambda _url, *, timeout: (
            """\
<html><body>
  <a class="list__item"
     href="/laisvos-darbo-vietos/436/skelbimas/DV-01-996740624">
    <div class="title"><strong>Veiklos procesų vadovas</strong></div>
    <div class="company">Example Operations, UAB</div>
    <div class="district">Vilniaus miesto sav.</div>
    <div class="location">Vilnius</div>
    <div class="created-date">Įkelta: 2026-07-24</div>
    <div class="contact">private.person@example.lt +370 612 34567</div>
  </a>
</body></html>
"""
        ),
    )

    result = sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {
                "max_records": 500,
                "live_fallback_enabled": True,
                "live_fallback_municipality_id": 461,
                "live_fallback_max_records": 100,
            },
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.status is None
    assert len(result.opportunities) == 1
    assert "open data was unavailable" in result.note
    row = result.opportunities[0]
    assert row.source_url.startswith("https://uzt.lt/")
    assert row.live_status == "live"
    assert "private.person" not in row.model_dump_json()
    assert "612 34567" not in row.model_dump_json()


def test_uzt_live_fallback_must_remain_on_official_domain(monkeypatch) -> None:
    monkeypatch.setattr(
        sources.providers,
        "fetch_json",
        lambda _url, *, timeout: {
            "_data": [
                {
                    "darbo_vietos_id": "DV-01-OLD",
                    "ikelimo_data": "2026-07-08",
                    "profesijos_pareigybes_pav": "Old vacancy",
                    "darbdavys": "Old employer",
                }
            ]
        },
    )
    live_fetch_called = False

    def fake_text_fetch(url: str, *, timeout: int) -> str:
        nonlocal live_fetch_called
        live_fetch_called = True
        return ""

    monkeypatch.setattr(sources.providers, "fetch_text", fake_text_fetch)

    with pytest.raises(ValueError, match="official HTTPS vacancy search"):
        sources.discover_uzt_open_data(
            _source_config(
                "uzt_open_data",
                {
                    "max_records": 500,
                    "max_feed_age_days": 3,
                    "live_fallback_url": "https://evil.example/results",
                },
            ),
            now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
        )

    assert live_fetch_called is False


def test_uzt_live_fallback_follows_bounded_official_pagination(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sources.providers,
        "fetch_json",
        lambda _url, *, timeout: {
            "_data": [
                {
                    "darbo_vietos_id": "DV-01-OLD",
                    "ikelimo_data": "2026-07-08",
                    "profesijos_pareigybes_pav": "Old vacancy",
                    "darbdavys": "Old employer",
                }
            ]
        },
    )
    seen_urls: list[str] = []

    def card(
        native_id: str,
        title: str,
        *,
        next_page: bool,
        page_prefix: str = "",
    ) -> str:
        next_link = (
            '<link rel="next" href="/laisvos-darbo-vietos/436/results/p100">'
            if next_page
            else ""
        )
        return f"""\
<html>
  <head>{next_link}</head>
  <body>
    <a class="list__item"
       href="/laisvos-darbo-vietos/436{page_prefix}/skelbimas/{native_id}">
      <div class="title">{title}</div>
      <div class="company">Example employer</div>
      <div class="district">Vilniaus miesto sav.</div>
      <div class="created-date">Įkelta: 2026-07-23</div>
    </a>
  </body>
</html>
"""

    def fake_text_fetch(url: str, *, timeout: int) -> str:
        seen_urls.append(url)
        if urlsplit(url).path.endswith("/p100"):
            return card(
                "DV-01-PAGE-2",
                "Second page",
                next_page=False,
                page_prefix="/p100",
            )
        return card("DV-01-PAGE-1", "First page", next_page=True)

    monkeypatch.setattr(sources.providers, "fetch_text", fake_text_fetch)
    result = sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {
                "max_records": 500,
                "max_feed_age_days": 3,
                "live_fallback_max_records": 200,
                "live_fallback_area_ids": [4, 103, 4],
            },
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert [urlsplit(url).path for url in seen_urls] == [
        "/laisvos-darbo-vietos/436/results",
        "/laisvos-darbo-vietos/436/results/p100",
    ]
    for url in seen_urls:
        assert parse_qs(urlsplit(url).query)["a[]"] == ["4", "103"]
    assert result.status is None
    assert result.complete is True
    assert [row.native_source_id for row in result.opportunities] == [
        "DV-01-PAGE-1",
        "DV-01-PAGE-2",
    ]


def test_uzt_stale_live_page_does_not_override_stale_open_data(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sources.providers,
        "fetch_json",
        lambda _url, *, timeout: {
            "_data": [
                {
                    "darbo_vietos_id": "DV-01-OLD",
                    "ikelimo_data": "2026-07-08",
                    "profesijos_pareigybes_pav": "Old vacancy",
                    "darbdavys": "Old employer",
                }
            ]
        },
    )
    stale_search = """\
<a class="list__item"
   href="/laisvos-darbo-vietos/436/skelbimas/DV-01-OLDER">
  <div class="title">Older vacancy</div>
  <div class="company">Older employer</div>
  <div class="district">Vilniaus miesto sav.</div>
  <div class="created-date">Įkelta: 2026-07-01</div>
</a>
"""
    monkeypatch.setattr(
        sources.providers,
        "fetch_text",
        lambda _url, *, timeout: stale_search,
    )

    result = sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {"max_records": 500, "max_feed_age_days": 3},
        ),
        now=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )

    assert result.status == "stale"
    assert result.opportunities[0].native_source_id == "DV-01-OLD"
    assert "did not provide a current page" in result.note


def test_uzt_deadline_filter_uses_vilnius_calendar_date(monkeypatch) -> None:
    seen_query: dict[str, list[str]] = {}

    def fake_fetch(url: str, *, timeout: int) -> dict[str, object]:
        seen_query.update(parse_qs(urlsplit(url).query))
        return {"_data": []}

    monkeypatch.setattr(sources.providers, "fetch_json", fake_fetch)
    sources.discover_uzt_open_data(
        _source_config(
            "uzt_open_data",
            {"max_records": 500, "live_fallback_enabled": False},
        ),
        now=datetime(2026, 7, 23, 23, 30, tzinfo=UTC),
    )

    assert seen_query["galioja_iki._ge"] == ['"2026-07-24"']
