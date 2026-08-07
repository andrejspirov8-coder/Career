from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from career_job_search.opportunities.dashboard_adapter import (
    build_opportunity_detail,
    build_opportunity_overview,
    build_weekly_roi_summary,
    record_opportunity_action,
)
from career_job_search.opportunities.live import (
    apply_daily_live_gate,
    classify_live_page,
)
from career_job_search.opportunities.matching import match_opportunities
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
    next_action_for_opportunity,
    utc_now_iso,
)
from career_job_search.opportunities.orchestrator import main as opportunity_main
from career_job_search.opportunities.repository import (
    get_opportunity,
    init_db,
    list_opportunities,
    mark_unseen_opportunities_expired,
    upsert_opportunities,
)
from career_job_search.opportunities.sources import (
    dedupe_opportunities,
    discover_opportunities,
    normalize_ats_posting,
)
from career_job_search.opportunities.text import (
    clean_opportunity_text,
    extract_deadline,
    extract_salary_text,
)


def write_job(path: Path, *, title: str = "Retail Operations Manager") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""TITLE: {title}
COMPANY: Example Retail
URL: https://example.com/jobs/retail-ops
SOURCE: company_site
JOB_ID: retail-ops
---
Lead premium retail operations in Vilnius with area management, store teams,
stock control, customer experience, and KPI ownership.
""",
        encoding="utf-8",
    )


def test_opportunity_model_validates_and_sets_dedupe_key() -> None:
    opportunity = Opportunity(
        source="inbox",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        source_url="https://example.com/jobs/role?utm=1",
        title="Area Manager",
        company="Example Retail",
        location="Vilnius",
        description="Retail leadership role",
    )

    assert opportunity.status == OpportunityStatus.NEW
    assert opportunity.dedupe_key == "url:https://example.com/jobs/role"
    assert opportunity.opportunity_id.startswith("opp_")


def test_manual_inbox_adapter_discovers_job_files(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "jobs"
    write_job(inbox / "retail.job.txt")

    discovered = discover_opportunities(
        {"opportunities": {"sources": {"inbox": {"enabled": True, "path": str(inbox)}}}}
    )

    assert len(discovered) == 1
    assert discovered[0].source_kind == OpportunitySourceKind.MANUAL_INBOX
    assert discovered[0].title == "Retail Operations Manager"
    assert discovered[0].company == "Example Retail"


def test_manual_inbox_adapter_skips_smoke_and_hidden_job_files(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "jobs"
    write_job(inbox / ".smoke-repo-123.job.txt", title="Smoke Test Job")
    write_job(inbox / "real-retail.job.txt", title="Retail Operations Manager")

    discovered = discover_opportunities(
        {"opportunities": {"sources": {"inbox": {"enabled": True, "path": str(inbox)}}}}
    )

    assert [row.title for row in discovered] == ["Retail Operations Manager"]


def test_ats_normalizers_support_greenhouse_and_lever() -> None:
    greenhouse = normalize_ats_posting(
        "greenhouse",
        {
            "id": 123,
            "title": "Store Director",
            "location": {"name": "Vilnius"},
            "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
            "content": "Luxury retail store leadership.",
        },
        company="Example Luxury",
    )
    lever = normalize_ats_posting(
        "lever",
        {
            "id": "abc",
            "text": "Operations Lead",
            "hostedUrl": "https://jobs.lever.co/example/abc",
            "categories": {"location": "Remote EU"},
            "descriptionPlain": "Operations management role.",
        },
        company="Example Ops",
    )

    assert greenhouse.title == "Store Director"
    assert greenhouse.source_kind == OpportunitySourceKind.ATS
    assert lever.title == "Operations Lead"
    assert lever.location == "Remote EU"


def test_live_ats_adapter_respects_source_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_json(url: str, *, timeout: int = 20) -> dict[str, object]:
        return {
            "jobs": [
                {
                    "id": idx,
                    "title": f"Operations Role {idx}",
                    "location": {"name": "Remote Europe"},
                    "absolute_url": f"https://boards.greenhouse.io/example/jobs/{idx}",
                    "content": "Operations and customer support workflows.",
                }
                for idx in range(5)
            ]
        }

    monkeypatch.setattr(
        "career_job_search.opportunities.sources.providers.fetch_json", fake_fetch_json
    )

    discovered = discover_opportunities(
        {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": False},
                    "ats": {
                        "enabled": True,
                        "providers": [
                            {
                                "provider": "greenhouse",
                                "company": "Example",
                                "board_token": "example",
                                "max_posts": 2,
                            }
                        ],
                    },
                }
            }
        }
    )

    assert [row.title for row in discovered] == [
        "Operations Role 0",
        "Operations Role 1",
    ]


def test_live_ats_adapters_discover_public_postings_without_applying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    def fake_fetch_json(url: str, *, timeout: int = 20) -> dict[str, object]:
        requested_urls.append(url)
        if "boards-api.greenhouse.io" in url:
            return {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Customer Operations Manager",
                        "location": {"name": "Vilnius"},
                        "absolute_url": "https://boards.greenhouse.io/vinted/jobs/1",
                        "content": "Lead customer operations, SLA, quality, and process improvement.",
                    }
                ]
            }
        if "api.lever.co" in url:
            return [
                {
                    "id": "lev-1",
                    "text": "Implementation Manager EMEA",
                    "hostedUrl": "https://jobs.lever.co/hightouch/lev-1",
                    "categories": {"location": "Remote Europe"},
                    "descriptionPlain": "Implementation, customer operations, stakeholders, and process design.",
                }
            ]
        if "api.ashbyhq.com" in url:
            return {
                "jobs": [
                    {
                        "id": "ash-1",
                        "title": "Business Process Operations Lead",
                        "jobUrl": "https://jobs.ashbyhq.com/deel/ash-1",
                        "location": "Remote EU",
                        "descriptionPlain": "Business process operations, support workflows, and vendor coordination.",
                    }
                ]
            }
        if "api.smartrecruiters.com" in url:
            return {
                "content": [
                    {
                        "id": "sr-1",
                        "name": "Retail Operations Lead",
                        "location": {"city": "London"},
                        "ref": {
                            "jobAd": "https://jobs.smartrecruiters.com/celine/sr-1"
                        },
                        "jobAd": "Retail operations, stock control, store standards, and KPIs.",
                    }
                ]
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(
        "career_job_search.opportunities.sources.providers.fetch_json", fake_fetch_json
    )

    discovered = discover_opportunities(
        {
            "opportunities": {
                "sources": {
                    "inbox": {"enabled": False},
                    "ats": {
                        "enabled": True,
                        "providers": [
                            {
                                "provider": "greenhouse",
                                "company": "Vinted",
                                "board_token": "vinted",
                            },
                            {
                                "provider": "lever",
                                "company": "Hightouch",
                                "company_slug": "hightouch",
                            },
                            {
                                "provider": "ashby",
                                "company": "Deel",
                                "job_board_name": "deel",
                            },
                            {
                                "provider": "smartrecruiters",
                                "company": "Celine",
                                "company_identifier": "celine",
                            },
                        ],
                    },
                }
            }
        }
    )

    assert [row.company for row in discovered] == [
        "Vinted",
        "Hightouch",
        "Deel",
    ]
    assert {row.source for row in discovered} == {
        "greenhouse:vinted",
        "lever:hightouch",
        "ashby:deel",
    }
    assert all(row.next_action != "apply_manual" for row in discovered)
    assert any("content=true" in url for url in requested_urls)
    assert any("api.lever.co/v0/postings/hightouch" in url for url in requested_urls)


def test_dedupe_merges_url_and_company_title_location_matches() -> None:
    rows = [
        Opportunity(
            source="a",
            source_kind=OpportunitySourceKind.JOB_BOARD,
            source_url="https://example.com/jobs/1",
            title="Operations Manager",
            company="Example",
            location="Vilnius",
            description="A",
        ),
        Opportunity(
            source="b",
            source_kind=OpportunitySourceKind.COMPANY_SITE,
            source_url="",
            title="operations manager",
            company="Example",
            location="Vilnius",
            description="B",
        ),
        Opportunity(
            source="c",
            source_kind=OpportunitySourceKind.WEB_SEARCH,
            source_url="https://example.com/jobs/1?utm=abc",
            title="Other",
            company="Other",
            location="Kaunas",
            description="C",
        ),
    ]

    unique = dedupe_opportunities(rows)

    assert len(unique) == 1
    assert "duplicate" in unique[0].evidence.risk_flags
    assert unique[0].duplicate_cluster_id == unique[0].opportunity_id


def test_match_opportunities_scores_and_sets_next_action(tmp_path: Path) -> None:
    job_file = tmp_path / "retail.job.txt"
    write_job(job_file)
    opportunity = discover_opportunities(
        {
            "opportunities": {
                "sources": {"inbox": {"enabled": True, "path": str(job_file.parent)}}
            }
        }
    )[0]

    matched = match_opportunities([opportunity])[0]

    assert matched.match is not None
    assert matched.match.best_variant
    assert matched.match.score > 0
    assert matched.next_action in {"make_pack", "tailor_cv", "review", "skip"}
    assert matched.match.runner_up_variant
    assert matched.match.runner_up_variant != matched.match.best_variant
    assert matched.match.variant_scores
    assert matched.match.variant_scores[0]["variant"] == matched.match.best_variant
    assert matched.match.variant_scores[1]["variant"] == matched.match.runner_up_variant
    assert "why_this_role" in matched.match.explanation


def test_lithuanian_cv_routing_keeps_variant_scores_aligned() -> None:
    opportunity = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        source_url="https://www.linkedin.com/jobs/view/1234567890",
        title="Parduotuvės vadovas",
        company="Example Retail",
        location="Vilniuje",
        description=(
            "Vadovauti parduotuvės komandai, klientų aptarnavimui, atsargoms, "
            "pardavimų KPI, procesų gerinimui ir kasdienėms operacijoms."
        ),
    )

    matched = match_opportunities([opportunity])[0]

    assert matched.match is not None
    assert matched.match.best_variant.endswith("-lt")
    assert matched.match.variant_scores[0]["variant"] == matched.match.best_variant
    assert matched.match.cv_score == matched.match.variant_scores[0]["primary_score"]
    assert matched.match.runner_up_variant != matched.match.best_variant
    assert (
        matched.match.runner_up_score
        == matched.match.variant_scores[1]["primary_score"]
    )


@pytest.mark.parametrize(
    "status",
    [
        OpportunityStatus.APPLIED,
        OpportunityStatus.SKIPPED,
        OpportunityStatus.APPLY_READY,
        OpportunityStatus.FOLLOW_UP,
    ],
)
def test_rematching_preserves_workflow_status(status: OpportunityStatus) -> None:
    opportunity = Opportunity(
        source="greenhouse:example",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://example.com/jobs/workflow-state",
        title="Customer Operations Manager",
        company="Example",
        location="Vilnius",
        description="Lead customer operations, quality, workflow, and stakeholders.",
        status=status,
    )

    matched = match_opportunities([opportunity])[0]

    assert matched.status == status


def test_match_opportunities_adds_fit_components_and_risk_flags() -> None:
    opportunity = Opportunity(
        source="greenhouse:vinted",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://boards.greenhouse.io/vinted/jobs/123",
        title="Customer Operations Manager - French speaking",
        company="Vinted",
        location="Remote Europe",
        salary_text="EUR 4,000-5,000 gross monthly",
        deadline="2026-12-30",
        description=(
            "Lead customer operations, SLA ownership, workflow improvement, "
            "quality management, stakeholder communication, and French language support."
        ),
    )

    matched = match_opportunities(
        [opportunity],
        scoring_config={
            "priority_regions": ["Lithuania", "Baltics", "Remote Europe", "Remote EU"],
            "role_tracks": [
                {
                    "name": "customer_operations",
                    "keywords": ["customer operations", "sla", "quality", "support"],
                }
            ],
        },
    )[0]

    assert matched.match is not None
    assert matched.match.cv_score > 0
    assert matched.match.location_score == 0
    assert matched.match.role_track_score > 0
    assert matched.match.source_score > 0
    assert matched.match.salary_score > 0
    assert matched.match.deadline_score > 0
    assert matched.match.fit_score >= matched.match.cv_score
    assert matched.match.role_track == "customer_operations"
    assert "language_requirement_risk" in matched.evidence.risk_flags
    assert "remote_eligibility_unverified" in matched.evidence.risk_flags
    assert matched.status == OpportunityStatus.REVIEW


def test_match_opportunities_demotes_obvious_technical_title_mismatch() -> None:
    opportunity = Opportunity(
        source="ashby:enode",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://jobs.ashbyhq.com/enode/data-engineer",
        title="Senior Data Engineer",
        company="Enode",
        location="Remote Europe",
        description=(
            "Business process operations, stakeholder communication, workflow "
            "documentation, implementation support, customer operations, SQL, "
            "reporting, data quality, and platform engineering."
        ),
    )

    matched = match_opportunities([opportunity])[0]

    assert matched.match is not None
    assert "role_family_mismatch" in matched.evidence.risk_flags
    assert matched.match.risk_penalty >= 8
    assert matched.status == OpportunityStatus.REVIEW


@pytest.mark.parametrize(
    "title",
    [
        "Associate Talent Partner",
        "GTM Recruiter",
        "Head of E-commerce",
        "Junior Investment Accounting Specialist",
        "Account Executive, North America",
    ],
)
def test_match_opportunities_blocks_unrelated_title_families(title: str) -> None:
    opportunity = Opportunity(
        source="greenhouse:example",
        source_kind=OpportunitySourceKind.ATS,
        source_url=f"https://example.com/jobs/{title.replace(' ', '-').lower()}",
        title=title,
        company="Example",
        location="Vilnius",
        description=(
            "Customer operations, business process improvement, stakeholder "
            "communication, quality, workflow, ERP, POS, and implementation."
        ),
    )

    matched = match_opportunities([opportunity])[0]

    assert matched.match is not None
    assert "role_family_mismatch" in matched.evidence.risk_flags
    assert matched.match.role_track == ""
    assert matched.next_action == "skip"


def test_job_text_cleanup_removes_markup_and_extracts_labelled_fields() -> None:
    raw = (
        "&lt;div&gt;&lt;h2&gt;About the role&lt;/h2&gt;&lt;p&gt;Lead operations."
        "&lt;/p&gt;&lt;/div&gt; - strong: Compensation: €3,000–€4,000 gross "
        "- text: Apply by 2026-08-15"
    )

    cleaned = clean_opportunity_text(raw)

    assert "<div" not in cleaned
    assert "strong:" not in cleaned
    assert "quot" not in cleaned
    assert "Lead operations" in cleaned
    assert extract_salary_text(cleaned) == "Compensation: €3,000–€4,000 gross"
    assert extract_deadline(cleaned) == "2026-08-15"


def test_live_page_classifier_handles_closed_active_and_unverified_pages() -> None:
    closed = classify_live_page(
        title='"PANDORA" vadovo asistentas',
        company="BRANDINC Jewellery / Pandora",
        visible_text=(
            "Negalioja Skelbimas neaktyvus Į šį skelbimą CV siųsti "
            "nebegalite. PANDORA vadovo asistentas Vilniuje."
        ),
    )
    cvbankas_closed = classify_live_page(
        title="Business Process Development Manager",
        company="EKSMA Optics",
        visible_text=(
            "Not valid Job ad is not active You cant candidate to this job ad "
            "anymore. Business Process Development Manager Vilnius."
        ),
    )
    cvonline_live = classify_live_page(
        title="Sr. Business Process Analyst",
        company="Dexcom Lithuania",
        visible_text=(
            "Sr. Business Process Analyst Dexcom Lithuania The Company "
            "Business process analyst responsibilities. Aplikuoti dabar."
        ),
    )
    ashby_live = classify_live_page(
        title="Client Delivery Lead",
        company="Enode",
        visible_text=(
            "Client Delivery Lead Location Remote - Europe Department Customer "
            "Success Overview Application Apply for this Job Enode."
        ),
    )
    vinted_live_with_recaptcha_text = classify_live_page(
        title="Vendor Operations Support Specialist",
        company="Vinted",
        visible_text=(
            "Vendor Operations Support Specialist Vinted Careers Vilnius "
            "Kaunas Community Support Apply now recaptcha_expired"
        ),
    )
    blocked = classify_live_page(
        title="Business Process Manager",
        company="Mediq",
        visible_text="Checking your browser before accessing this site.",
    )
    linkedin_authwall = classify_live_page(
        title="Business Process Manager",
        company="Mediq",
        visible_text=(
            "LinkedIn authwall Sign in to LinkedIn Business Process Manager Apply now"
        ),
    )
    empty = classify_live_page(
        title="Business Process Manager",
        company="Mediq",
        visible_text="",
    )

    assert closed.status == "closed"
    assert cvbankas_closed.status == "closed"
    assert cvonline_live.status == "live"
    assert ashby_live.status == "live"
    assert vinted_live_with_recaptcha_text.status == "live"
    assert blocked.status == "unverified"
    assert linkedin_authwall.note == "login_or_access_wall"
    assert linkedin_authwall.status == "unverified"
    assert empty.status == "unverified"


def test_current_browser_verified_linkedin_job_skips_cookie_less_http_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        source_url="https://www.linkedin.com/jobs/view/4438191493",
        title="Partner Performance Specialist, CS Operations",
        company="Vinted",
        location="Vilnius",
        live_status="live",
        live_checked_at=utc_now_iso(),
        live_check_method="linkedin_browser",
        live_check_note="browser_job_card_and_detail",
        status=OpportunityStatus.MATCHED,
    )
    row.match = OpportunityMatch(
        best_variant="it-business",
        score=20,
        fit_score=20,
        cv_score=12,
    )

    def should_not_fetch(*_args, **_kwargs):
        raise AssertionError(
            "browser-verified LinkedIn row was rechecked without cookies"
        )

    monkeypatch.setattr(
        "career_job_search.opportunities.live.fetch_public_page_text", should_not_fetch
    )

    checked = apply_daily_live_gate([row], fresh_dedupe_keys=[])

    assert checked[0].live_status == "live"
    assert checked[0].live_check_method == "linkedin_browser"


def test_daily_live_gate_marks_ats_live_and_manual_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ats = Opportunity(
        source="ashby:enode",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://jobs.ashbyhq.com/enode/live",
        title="Client Delivery Lead",
        company="Enode",
        location="Remote Europe",
        description="Customer operations and delivery ownership.",
        status=OpportunityStatus.MATCHED,
    )
    manual = Opportunity(
        source="manual_inbox",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        source_url="https://www.cvbankas.lt/closed",
        title='"PANDORA" vadovo asistentas',
        company="Pandora",
        location="Vilnius",
        description="Retail operations role.",
        status=OpportunityStatus.MATCHED,
    )
    for row in (ats, manual):
        row.match = OpportunityMatch(
            best_variant="operations-management",
            score=20,
            fit_score=20,
            cv_score=14,
            location_score=4,
            role_track_score=2,
            source_score=2,
            confidence="clear_winner",
        )

    def fake_fetch_public_page_text(url: str, *, timeout: int = 10) -> tuple[int, str]:
        assert url == "https://www.cvbankas.lt/closed"
        return 200, "Negalioja Skelbimas neaktyvus CV siųsti nebegalite PANDORA"

    monkeypatch.setattr(
        "career_job_search.opportunities.live.fetch_public_page_text",
        fake_fetch_public_page_text,
    )

    gated = apply_daily_live_gate(
        [ats, manual],
        fresh_dedupe_keys=[ats.dedupe_key, manual.dedupe_key],
        max_page_checks=5,
    )

    by_id = {row.opportunity_id: row for row in gated}
    assert by_id[ats.opportunity_id].live_status == "live"
    assert by_id[ats.opportunity_id].live_check_method == "ats_feed"
    assert by_id[manual.opportunity_id].live_status == "closed"
    assert by_id[manual.opportunity_id].status == OpportunityStatus.EXPIRED
    assert by_id[manual.opportunity_id].likely_closed is True


def test_state_tracks_freshness_updates_and_likely_closed_rows(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    initial = Opportunity(
        source="greenhouse:vinted",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://boards.greenhouse.io/vinted/jobs/1",
        title="Operations Manager",
        company="Vinted",
        location="Vilnius",
        description="Initial operations role description.",
    )
    upsert_opportunities([initial], db_path=db)
    first_seen = get_opportunity(initial.opportunity_id, db_path=db).first_seen_at  # type: ignore[union-attr]

    updated = Opportunity(
        source="greenhouse:vinted",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://boards.greenhouse.io/vinted/jobs/1",
        title="Operations Manager",
        company="Vinted",
        location="Vilnius",
        description="Updated operations role description with customer workflows.",
    )
    upsert_opportunities([updated], db_path=db)

    stored = get_opportunity(initial.opportunity_id, db_path=db)
    assert stored is not None
    assert stored.first_seen_at == first_seen
    assert stored.last_seen_at >= stored.first_seen_at
    assert stored.last_checked_at >= stored.first_seen_at
    assert stored.source_updated_at
    assert "role_updated" in stored.evidence.risk_flags

    expired_count = mark_unseen_opportunities_expired(
        seen_dedupe_keys=[],
        source_names=["greenhouse:vinted"],
        db_path=db,
    )
    expired = get_opportunity(initial.opportunity_id, db_path=db)
    assert expired_count == 1
    assert expired is not None
    assert expired.status == OpportunityStatus.EXPIRED
    assert expired.likely_closed is True
    assert "likely_closed" in expired.evidence.risk_flags


def test_state_persists_and_updates_opportunities(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    init_db(db)
    opportunity = Opportunity(
        source="inbox",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        title="Area Manager",
        company="Example Retail",
        location="Vilnius",
        description="Retail area role",
    )

    upsert_opportunities([opportunity], db_path=db)
    record_opportunity_action(
        action_type="mark_apply_ready",
        opportunity_id=opportunity.opportunity_id,
        db_path=db,
        operator_source="test",
    )

    stored = get_opportunity(opportunity.opportunity_id, db_path=db)
    assert stored is not None
    assert stored.status == OpportunityStatus.APPLY_READY
    assert (
        list_opportunities(db_path=db)[0].opportunity_id == opportunity.opportunity_id
    )


def test_dashboard_overview_saved_views_and_safe_pack_action(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    pack_dir = tmp_path / "packs"
    job_file = tmp_path / "jobs" / "retail.job.txt"
    write_job(job_file)
    opportunity = match_opportunities(
        discover_opportunities(
            {
                "opportunities": {
                    "sources": {
                        "inbox": {"enabled": True, "path": str(job_file.parent)}
                    }
                }
            }
        )
    )[0]
    opportunity.status = OpportunityStatus.APPLY_READY
    upsert_opportunities([opportunity], db_path=db)

    generated = record_opportunity_action(
        action_type="generate_pack",
        opportunity_id=opportunity.opportunity_id,
        db_path=db,
        packs_dir=pack_dir,
        operator_source="test",
    )
    overview = build_opportunity_overview(db_path=db)
    detail = build_opportunity_detail(opportunity.opportunity_id, db_path=db)

    assert generated["generated"] is True
    assert Path(generated["pack_dir"]).exists()
    assert overview["schema"] == "opportunity_dashboard_overview_v2"
    assert overview["queues"]["saved_views"]["apply_ready"] == [
        opportunity.opportunity_id
    ]
    summary = overview["queues"]["all"][0]
    assert summary["has_pack"] is True
    assert "description" not in summary
    assert detail["opportunity_id"] == opportunity.opportunity_id
    assert detail["description"]
    assert detail["action_history"]
    assert "new_today" in overview["queues"]["saved_views"]
    assert "best_europe_matches" in overview["queues"]["saved_views"]
    assert "apply_today" in overview["queues"]["saved_views"]
    assert "missing_outcome" in overview["queues"]["saved_views"]
    assert "follow_up" in overview["queues"]["saved_views"]
    assert "closing_soon" in overview["queues"]["saved_views"]
    assert "likely_duplicate" in overview["queues"]["saved_views"]
    assert "likely_expired" in overview["queues"]["saved_views"]
    assert overview["safe_actions"] == [
        "mark_review",
        "mark_skipped",
        "mark_apply_ready",
        "generate_pack",
        "mark_applied",
        "log_application",
        "update_application_outcome",
        "snooze_followup",
        "undo_last_decision",
    ]


def test_dashboard_overview_is_compact_and_saved_views_use_ids(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    opportunity = Opportunity(
        opportunity_id="opp_compact",
        source="greenhouse:example",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://example.com/jobs/compact",
        title="Customer Operations Manager",
        company="Example",
        location="Vilnius",
        description="Detailed customer operations evidence. " * 500,
        status=OpportunityStatus.REVIEW,
    )
    opportunity.location_eligibility = "eligible_vilnius"
    opportunity.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=18,
        fit_score=18,
        cv_score=12,
        role_track="customer_operations",
        confidence="tie_review",
    )
    opportunity.live_status = "live"
    opportunity.live_checked_at = utc_now_iso()
    upsert_opportunities([opportunity], db_path=db)

    overview = build_opportunity_overview(db_path=db)
    detail = build_opportunity_detail(opportunity.opportunity_id, db_path=db)
    legacy_shape = {
        "queues": {
            "all": [detail],
            "saved_views": {
                name: [detail] if opportunity.opportunity_id in ids else []
                for name, ids in overview["queues"]["saved_views"].items()
            },
        }
    }

    assert overview["queues"]["all"][0]["opportunity_id"] == "opp_compact"
    assert "description" not in overview["queues"]["all"][0]
    assert all(
        isinstance(opportunity_id, str)
        for ids in overview["queues"]["saved_views"].values()
        for opportunity_id in ids
    )
    assert len(json.dumps(overview)) <= len(json.dumps(legacy_shape)) * 0.25


def test_needs_review_excludes_blocked_and_ineligible_rows(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"

    def review_row(
        opportunity_id: str, *, flags: list[str], eligibility: str
    ) -> Opportunity:
        row = Opportunity(
            opportunity_id=opportunity_id,
            source="greenhouse:example",
            source_kind=OpportunitySourceKind.ATS,
            source_url=f"https://example.com/jobs/{opportunity_id}",
            title="Operations Manager",
            company=f"Example {opportunity_id}",
            location="Vilnius",
            description="Lead customer operations, quality, workflow, and stakeholders.",
            status=OpportunityStatus.REVIEW,
        )
        row.location_eligibility = eligibility
        row.evidence.risk_flags = flags
        row.match = OpportunityMatch(score=12, fit_score=12, cv_score=9)
        return row

    actionable = review_row(
        "opp_actionable",
        flags=["remote_eligibility_unverified"],
        eligibility="verify_remote",
    )
    mismatch = review_row(
        "opp_mismatch",
        flags=["role_family_mismatch"],
        eligibility="eligible_vilnius",
    )
    ineligible = review_row(
        "opp_ineligible",
        flags=["location_ineligible"],
        eligibility="ineligible",
    )
    upsert_opportunities([actionable, mismatch, ineligible], db_path=db)

    overview = build_opportunity_overview(db_path=db)

    assert overview["queues"]["saved_views"]["needs_review"] == ["opp_actionable"]
    assert set(overview["queues"]["saved_views"]["blockers"]) == {
        "opp_mismatch",
        "opp_ineligible",
    }


def test_dashboard_best_views_hide_noisy_rows_and_surface_daily_queue(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"

    def row(
        opportunity_id: str,
        *,
        status: OpportunityStatus,
        flags: list[str] | None = None,
        next_action: str = "make_pack",
        score: float = 18.0,
    ) -> Opportunity:
        opportunity = Opportunity(
            opportunity_id=opportunity_id,
            source="greenhouse:vinted",
            source_kind=OpportunitySourceKind.ATS,
            source_url=f"https://example.com/jobs/{opportunity_id}",
            title=f"Role {opportunity_id}",
            company="Example",
            location="Vilnius",
            description="Customer operations, quality, workflow, and stakeholder role.",
            status=status,
        )
        opportunity.match = OpportunityMatch(
            best_variant="business-process-operations",
            score=score,
            fit_score=score,
            cv_score=score - 4,
            location_score=4,
            role_track_score=2,
            source_score=3,
            confidence="clear_winner",
            margin_over_second=6,
        )
        opportunity.evidence.risk_flags = flags or []
        opportunity.live_status = "live"
        opportunity.live_checked_at = utc_now_iso()
        opportunity.live_check_method = "test"
        opportunity.next_action = next_action
        return opportunity

    clean = row("opp_clean", status=OpportunityStatus.APPLY_READY)
    weak_location = row(
        "opp_weak_location",
        status=OpportunityStatus.APPLY_READY,
        flags=["weak_location_fit"],
        score=32,
    )
    low_score = row(
        "opp_low_score",
        status=OpportunityStatus.MATCHED,
        flags=["low_cv_score"],
        score=22,
    )
    tailoring = row(
        "opp_tailor",
        status=OpportunityStatus.MATCHED,
        next_action="tailor_cv",
        score=13,
    )
    assert tailoring.match is not None
    tailoring.match.margin_over_second = 2
    applied = row("opp_applied", status=OpportunityStatus.APPLIED)
    follow_up = row("opp_follow_up", status=OpportunityStatus.FOLLOW_UP)

    upsert_opportunities(
        [clean, weak_location, low_score, tailoring, applied, follow_up],
        db_path=db,
    )

    saved_views = build_opportunity_overview(db_path=db)["queues"]["saved_views"]

    assert saved_views["best_matches"] == ["opp_clean"]
    assert saved_views["apply_today"] == ["opp_clean"]
    assert set(saved_views["needs_cv_tailoring"]) == {"opp_tailor"}
    assert saved_views["missing_outcome"] == ["opp_applied"]
    assert saved_views["follow_up"] == ["opp_follow_up"]


def test_dashboard_top_5_today_ranks_clean_high_fit_work(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"

    def row(
        opportunity_id: str,
        *,
        status: OpportunityStatus = OpportunityStatus.MATCHED,
        next_action: str = "review",
        score: float = 18.0,
        location: str = "Remote Europe",
        flags: list[str] | None = None,
    ) -> Opportunity:
        opportunity = Opportunity(
            opportunity_id=opportunity_id,
            source="greenhouse:vinted",
            source_kind=OpportunitySourceKind.ATS,
            source_url=f"https://example.com/jobs/{opportunity_id}",
            title=f"Role {opportunity_id}",
            company="Example",
            location=location,
            description="Customer operations, quality, workflow, and stakeholder role.",
            status=status,
        )
        opportunity.match = OpportunityMatch(
            best_variant="business-process-operations",
            score=score,
            fit_score=score,
            cv_score=score - 4,
            location_score=4,
            role_track_score=2,
            source_score=3,
            confidence="clear_winner",
            margin_over_second=6,
        )
        opportunity.evidence.risk_flags = flags or []
        opportunity.live_status = "live"
        opportunity.live_checked_at = utc_now_iso()
        opportunity.live_check_method = "test"
        opportunity.next_action = next_action
        return opportunity

    apply_ready = row(
        "opp_apply_ready",
        status=OpportunityStatus.APPLY_READY,
        next_action="make_pack",
        score=21,
    )
    tailor_high_fit = row("opp_tailor_high_fit", next_action="tailor_cv", score=19)
    clean_match = row("opp_clean_match", next_action="review", score=17)
    low_cv = row(
        "opp_low_cv",
        next_action="tailor_cv",
        score=30,
        flags=["low_cv_score"],
    )
    weak_location = row(
        "opp_weak_location",
        next_action="review",
        score=28,
        location="Remote US",
        flags=["weak_location_fit"],
    )
    unverified = row(
        "opp_unverified",
        next_action="review",
        score=35,
        flags=["needs_live_verification"],
    )
    unverified.source_kind = OpportunitySourceKind.MANUAL_INBOX
    unverified.live_status = "unverified"
    unverified.live_check_note = "matching_role_without_apply_signal"
    already_applied = row(
        "opp_already_applied",
        status=OpportunityStatus.APPLIED,
        next_action="follow_up",
        score=40,
    )

    upsert_opportunities(
        [
            apply_ready,
            tailor_high_fit,
            clean_match,
            low_cv,
            weak_location,
            unverified,
            already_applied,
        ],
        db_path=db,
    )

    overview = build_opportunity_overview(db_path=db)
    top_ids = overview["queues"]["saved_views"]["top_5_today"]

    assert top_ids == ["opp_apply_ready", "opp_tailor_high_fit", "opp_clean_match"]
    assert overview["counts"]["top_5_today"] == 3
    assert overview["queues"]["saved_views"]["needs_live_verification"] == [
        "opp_unverified"
    ]


def test_dashboard_fresh_live_matches_excludes_previously_seen_jobs(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"

    def live_match(opportunity_id: str, *, first_seen_at: str) -> Opportunity:
        opportunity = Opportunity(
            opportunity_id=opportunity_id,
            source="greenhouse:example",
            source_kind=OpportunitySourceKind.ATS,
            source_url=f"https://example.com/jobs/{opportunity_id}",
            title=f"Operations Role {opportunity_id}",
            company="Example",
            location="Remote Europe",
            description="Customer operations, quality, workflow, and stakeholder role.",
            first_seen_at=first_seen_at,
            status=OpportunityStatus.MATCHED,
        )
        opportunity.match = OpportunityMatch(
            best_variant="business-process-operations",
            score=18,
            fit_score=18,
            cv_score=12,
            location_score=4,
            role_track_score=2,
            source_score=3,
            confidence="clear_winner",
            margin_over_second=6,
        )
        opportunity.live_status = "live"
        opportunity.live_checked_at = utc_now_iso()
        opportunity.live_check_method = "test"
        opportunity.next_action = "review"
        return opportunity

    fresh = live_match("opp_fresh", first_seen_at=utc_now_iso())
    previously_seen = live_match(
        "opp_previously_seen",
        first_seen_at="2026-01-01T08:00:00+00:00",
    )
    upsert_opportunities([fresh, previously_seen], db_path=db)

    saved_views = build_opportunity_overview(db_path=db)["queues"]["saved_views"]

    assert saved_views["fresh_live_matches"] == ["opp_fresh"]
    assert set(saved_views["top_5_today"]) == {
        "opp_fresh",
        "opp_previously_seen",
    }


def test_official_alert_live_evidence_survives_vilnius_midnight(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    vilnius_now = datetime.now(ZoneInfo("Europe/Vilnius"))
    previous_local_day = vilnius_now.replace(
        hour=23, minute=59, second=0, microsecond=0
    ) - timedelta(days=1)
    opportunity = Opportunity(
        opportunity_id="opp_recent_alert",
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_ALERT,
        source_url="https://www.linkedin.com/jobs/view/1234567890",
        title="Operations Lead",
        company="Example",
        location="Vilnius",
        location_eligibility="eligible_vilnius",
        description="Customer operations, quality, workflow, and stakeholder role.",
        status=OpportunityStatus.MATCHED,
        live_status="live",
        live_checked_at=previous_local_day.isoformat(),
        live_check_method="official_job_alert",
    )
    opportunity.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=30,
        fit_score=30,
        cv_score=12,
        confidence="clear_winner",
        margin_over_second=6,
    )
    opportunity.next_action = "review"
    upsert_opportunities([opportunity], db_path=db)

    saved_views = build_opportunity_overview(db_path=db)["queues"]["saved_views"]

    assert saved_views["delivery_candidates"] == ["opp_recent_alert"]


def test_top_today_keeps_strong_tie_review_cv_matches_for_human_choice(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    opportunity = Opportunity(
        opportunity_id="opp_tie_review",
        source="greenhouse:example",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://example.com/jobs/tie-review",
        title="Operations Lead",
        company="Example",
        location="Vilnius",
        description="Customer operations, quality, workflow, and stakeholder role.",
        status=OpportunityStatus.MATCHED,
    )
    opportunity.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=30,
        fit_score=30,
        cv_score=12,
        confidence="tie_review",
        margin_over_second=2,
    )
    opportunity.live_status = "live"
    opportunity.live_checked_at = utc_now_iso()
    opportunity.live_check_method = "test"
    opportunity.next_action = "review"
    upsert_opportunities([opportunity], db_path=db)

    saved_views = build_opportunity_overview(db_path=db)["queues"]["saved_views"]

    assert saved_views["top_5_today"] == ["opp_tie_review"]


def test_card_only_linkedin_capture_is_not_a_delivery_candidate(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    opportunity = Opportunity(
        opportunity_id="opp_card_only",
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        source_url="https://www.linkedin.com/jobs/view/1234567890",
        title="Operations Lead",
        company="Example",
        location="Vilnius",
        location_eligibility="eligible_vilnius",
        description="Customer operations, quality, workflow, and stakeholder role.",
        status=OpportunityStatus.MATCHED,
        live_status="live",
        live_checked_at=utc_now_iso(),
        live_check_method="linkedin_browser",
    )
    opportunity.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=30,
        fit_score=30,
        cv_score=12,
        confidence="clear_winner",
        margin_over_second=6,
    )
    opportunity.evidence.source_facts = ["chrome:linkedin_jobs_search"]
    opportunity.next_action = "review"
    upsert_opportunities([opportunity], db_path=db)

    saved_views = build_opportunity_overview(db_path=db)["queues"]["saved_views"]

    assert saved_views["delivery_candidates"] == []


def test_log_application_from_opportunity_appends_tracking_row(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    applications_csv = tmp_path / "applications.csv"
    opportunity = Opportunity(
        opportunity_id="opp_loggable",
        source="greenhouse:vinted",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://example.com/jobs/opp-loggable",
        title="Customer Operations Manager",
        company="Vinted",
        location="Remote Europe",
        salary_text="EUR 4,000-5,000 gross monthly",
        deadline="2026-07-15",
        description="Customer operations, quality, workflow, and stakeholder role.",
        status=OpportunityStatus.APPLY_READY,
    )
    opportunity.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=18,
        fit_score=18,
        cv_score=12,
        location_score=4,
        role_track_score=2,
        source_score=3,
        confidence="clear_winner",
    )
    opportunity.pack = None
    opportunity.next_action = "make_pack"
    upsert_opportunities([opportunity], db_path=db)

    result = record_opportunity_action(
        action_type="log_application",
        opportunity_id=opportunity.opportunity_id,
        db_path=db,
        applications_csv=applications_csv,
        application_url="https://apply.example.com/123",
        operator_source="test",
    )

    stored = get_opportunity(opportunity.opportunity_id, db_path=db)
    rows = list(csv.DictReader(applications_csv.open(encoding="utf-8")))

    assert result["application_logged"] is True
    assert stored is not None
    assert stored.status == OpportunityStatus.APPLIED
    assert stored.next_action == "follow_up"
    assert rows == [
        {
            "date_iso": result["date_iso"],
            "company": "Vinted",
            "title": "Customer Operations Manager",
            "variant_slug": "business-process-operations",
            "source": "greenhouse:vinted",
            "outcome": "applied",
            "deadline_date": "2026-07-15",
            "match_score": "18",
            "match_confidence": "clear_winner",
            "salary_range": "EUR 4,000-5,000 gross monthly",
            "tailored_cv": "no",
            "response_date": "",
            "opportunity_id": "opp_loggable",
            "pack_dir": "",
            "application_url": "https://apply.example.com/123",
            "notes": "Logged from opportunity queue; actual application submitted manually.",
        }
    ]


def test_application_outcome_updates_latest_log_and_pipeline_status(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    applications_csv = tmp_path / "applications.csv"
    opportunity = Opportunity(
        opportunity_id="opp_outcome",
        source="greenhouse:vinted",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://example.com/jobs/outcome",
        title="Customer Operations Manager",
        company="Vinted",
        location="Vilnius",
        description="Customer operations and quality leadership.",
        status=OpportunityStatus.APPLY_READY,
    )
    opportunity.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=18,
        fit_score=18,
        cv_score=12,
    )
    upsert_opportunities([opportunity], db_path=db)
    record_opportunity_action(
        action_type="log_application",
        opportunity_id=opportunity.opportunity_id,
        db_path=db,
        applications_csv=applications_csv,
        application_notes="Submitted through the company careers page.",
        operator_source="test",
    )

    result = record_opportunity_action(
        action_type="update_application_outcome",
        opportunity_id=opportunity.opportunity_id,
        db_path=db,
        applications_csv=applications_csv,
        application_outcome="interview",
        operator_source="test",
    )

    stored = get_opportunity(opportunity.opportunity_id, db_path=db)
    rows = list(csv.DictReader(applications_csv.open(encoding="utf-8")))
    assert result["application_updated"] is True
    assert rows[-1]["outcome"] == "interview"
    assert rows[-1]["response_date"]
    assert rows[-1]["notes"] == "Submitted through the company careers page."
    assert stored is not None
    assert stored.status == OpportunityStatus.FOLLOW_UP


def test_weekly_roi_summary_flags_conversion_gaps(tmp_path: Path) -> None:
    applications_csv = tmp_path / "applications.csv"
    recruiters_csv = tmp_path / "recruiters.csv"
    applications_csv.write_text(
        "\n".join(
            [
                (
                    "date_iso,company,title,variant_slug,source,outcome,"
                    "deadline_date,match_score,match_confidence,salary_range,"
                    "tailored_cv,response_date,opportunity_id,pack_dir,"
                    "application_url,notes"
                ),
                (
                    "2026-06-26,Vinted,Role A,business-process-operations,"
                    "greenhouse:vinted,applied,,18,clear_winner,,yes,,opp_a,,,"
                ),
                (
                    "2026-06-27,Airalo,Role B,luxury-retail,lever:airalo,"
                    "interview,,12,review,,no,2026-06-29,opp_b,,,"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    recruiters_csv.write_text(
        "\n".join(
            [
                "profile_url,status,accepted_at,reply_at,interview_at",
                "https://www.linkedin.com/in/a,sent,,,",
                "https://www.linkedin.com/in/b,sent,2026-06-28,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_weekly_roi_summary(
        applications_csv=applications_csv,
        recruiters_csv=recruiters_csv,
    )

    assert summary["applications"]["submitted"] == 2
    assert summary["applications"]["interviews"] == 1
    assert summary["applications"]["missing_outcome"] == 1
    assert summary["applications"]["best_sources"][0]["source"] == "lever:airalo"
    assert summary["applications"]["worst_sources"][0]["source"] == "greenhouse:vinted"
    assert summary["recruiters"]["sent"] == 2
    assert summary["recruiters"]["missing_accepted_at"] == 1
    assert summary["recruiters"]["missing_reply_at"] == 2
    assert summary["recruiters"]["missing_interview_at"] == 2
    assert summary["next_roi_action"] == "Update missing application outcomes first."


def test_orchestrate_discover_dry_run_outputs_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inbox = tmp_path / "jobs"
    write_job(inbox / "retail.job.txt")
    config = tmp_path / "opportunities.yaml"
    config.write_text(
        f"""
opportunities:
  sources:
    inbox:
      enabled: true
      path: {inbox}
""",
        encoding="utf-8",
    )

    rc = opportunity_main(["--config", str(config), "discover", "--dry-run"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["ok"] is True
    assert out["data"]["count"] == 1


def test_orchestrate_missing_explicit_config_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing-opportunities.yaml"

    rc = opportunity_main(["--config", str(missing), "discover", "--dry-run"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert out["ok"] is False
    assert str(missing) in out["error"]
    assert "not found" in out["error"].lower()


def test_orchestrate_daily_queue_outputs_concise_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inbox = tmp_path / "jobs"
    write_job(inbox / "retail.job.txt")
    config = tmp_path / "opportunities.yaml"
    db = tmp_path / "opportunities.sqlite3"
    config.write_text(
        f"""
opportunities:
  sources:
    inbox:
      enabled: true
      path: {inbox}
""",
        encoding="utf-8",
    )

    rc = opportunity_main(["--config", str(config), "--db", str(db), "daily-queue"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["ok"] is True
    assert out["data"]["discovered"] == 1
    assert out["data"]["matched"] == 1
    assert "opportunities" not in out["data"]
    assert "apply_today" in out["data"]["counts"]
    assert "top_5_today" in out["data"]["review_queue"]


def test_orchestrate_report_summary_excludes_raw_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    opportunity = Opportunity(
        source="inbox",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        title="Area Manager",
        company="Example",
        location="Vilnius",
        description="Retail area role",
        status=OpportunityStatus.MATCHED,
    )
    opportunity.match = OpportunityMatch(
        best_variant="operations-management",
        score=18,
        fit_score=18,
        cv_score=12,
        location_score=4,
        role_track_score=2,
        source_score=0,
        confidence="clear_winner",
        margin_over_second=6,
    )
    opportunity.live_status = "live"
    opportunity.live_checked_at = utc_now_iso()
    opportunity.live_check_method = "test"
    opportunity.next_action = "review"
    upsert_opportunities([opportunity], db_path=db)

    rc = opportunity_main(["--db", str(db), "report", "--summary"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["ok"] is True
    assert out["data"]["counts"]["total"] == 1
    assert "queues" not in out["data"]
    assert out["data"]["review_queue"]["fresh_live_matches"] == 1
    assert (
        out["data"]["fresh_live_matches"][0]["opportunity_id"]
        == opportunity.opportunity_id
    )
    assert out["data"]["top_5_today"][0]["opportunity_id"] == opportunity.opportunity_id


def test_next_action_never_auto_applies() -> None:
    opportunity = Opportunity(
        source="inbox",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        title="Area Manager",
        company="Example",
        description="Retail area role",
        status=OpportunityStatus.APPLY_READY,
    )

    assert next_action_for_opportunity(opportunity) == "make_pack"
