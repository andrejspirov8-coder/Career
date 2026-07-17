from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import opportunity_state as state
from opportunity_browser import opportunity_from_browser_job
from opportunity_models import (
    Opportunity,
    OpportunityPack,
    OpportunitySourceKind,
    OpportunityStatus,
    company_title_location_key,
)


def opportunity(
    *,
    source: str = "greenhouse:example",
    native_source_id: str = "",
    source_url: str = "https://jobs.example.com/roles/1",
    title: str = "Operations Lead",
    company: str = "Example",
    location: str = "Remote EU",
    description: str = "Lead customer operations.",
    status: OpportunityStatus = OpportunityStatus.NEW,
) -> Opportunity:
    return Opportunity(
        source=source,
        source_kind=OpportunitySourceKind.ATS,
        native_source_id=native_source_id,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        description=description,
        status=status,
    )


def table_names(db: Path) -> set[str]:
    with sqlite3.connect(db) as con:
        return {
            str(row[0])
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def test_model_loads_legacy_json_and_fills_durable_identity() -> None:
    legacy = Opportunity.model_validate(
        {
            "source": "legacy-board",
            "source_kind": "job_board",
            "source_url": "https://example.com/jobs/old?tracking=1",
            "title": "Area Manager",
            "company": "Example Retail",
            "location": "Vilnius",
        }
    )
    native = opportunity(
        native_source_id="GH-123",
        source_url="https://jobs.example.com/roles/old-url",
    )

    assert OpportunitySourceKind.JOB_ALERT.value == "job_alert"
    assert legacy.location_eligibility == ""
    assert legacy.eligibility_reason == ""
    assert legacy.first_eligible_at == ""
    assert legacy.native_source_id == ""
    assert legacy.canonical_identity == company_title_location_key(
        "Example Retail", "Area Manager", "Vilnius"
    )
    assert not legacy.canonical_identity.startswith("url:")
    assert native.canonical_identity.startswith("native:")
    assert "gh-123" in native.canonical_identity


def test_schema_migration_is_idempotent_and_preserves_existing_rows(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute(
            """
            CREATE TABLE opportunities (
              opportunity_id TEXT PRIMARY KEY,
              dedupe_key TEXT NOT NULL,
              source_kind TEXT NOT NULL,
              source_url TEXT,
              title TEXT,
              company TEXT,
              location TEXT,
              status TEXT NOT NULL,
              data_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            INSERT INTO opportunities VALUES (
              'opp_existing', 'url:https://example.com/1', 'job_board',
              'https://example.com/1', 'Existing', 'Example', 'Vilnius',
              'new', '{}', '2026-07-01T00:00:00+00:00',
              '2026-07-01T00:00:00+00:00'
            )
            """
        )

    state.init_db(db)
    state.init_db(db)

    assert {
        "source_runs",
        "daily_runs",
        "opportunity_aliases",
        "deliveries",
    } <= table_names(db)
    with sqlite3.connect(db) as con:
        count = con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    assert count == 1


@pytest.mark.parametrize(
    "status",
    [
        OpportunityStatus.APPLIED,
        OpportunityStatus.SKIPPED,
        OpportunityStatus.FOLLOW_UP,
        OpportunityStatus.APPLY_READY,
    ],
)
def test_fresh_content_preserves_workflow_state_dates_and_pack(
    tmp_path: Path,
    status: OpportunityStatus,
) -> None:
    db = tmp_path / f"{status.value}.sqlite3"
    initial = opportunity(
        native_source_id="stable-1",
        description="Original description.",
        status=status,
    )
    initial.discovered_at = "2026-06-01T08:00:00+00:00"
    initial.first_seen_at = "2026-06-01T08:00:00+00:00"
    initial.pack = OpportunityPack(pack_id="pack-1", pack_dir="/tmp/pack-1")
    state.upsert_opportunities([initial], db_path=db)

    fresh = opportunity(
        native_source_id="stable-1",
        description="Materially changed description.",
    )
    state.upsert_opportunities([fresh], db_path=db)

    stored = state.get_opportunity(initial.opportunity_id, db_path=db)
    assert stored is not None
    assert stored.status == status
    assert stored.discovered_at == "2026-06-01T08:00:00+00:00"
    assert stored.first_seen_at == "2026-06-01T08:00:00+00:00"
    assert stored.pack is not None
    assert stored.pack.pack_id == "pack-1"
    assert "role_updated" in stored.evidence.risk_flags


def test_save_opportunity_does_not_advance_last_seen(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = opportunity(native_source_id="stable-1")
    row.last_seen_at = "2026-06-01T08:00:00+00:00"

    state.save_opportunity(row, db_path=db)

    stored = state.get_opportunity(row.opportunity_id, db_path=db)
    assert stored is not None
    assert stored.last_seen_at == "2026-06-01T08:00:00+00:00"


def test_linkedin_card_refresh_preserves_detail_description(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    detail_payload = {
        "source": "linkedin",
        "captured_at": "2026-07-10T16:30:00+00:00",
        "url": "https://www.linkedin.com/jobs/view/4430447179",
        "title": "Retail Manager | $65/hr Remote",
        "company": "Crossing Hurdles",
        "location": "European Union (Remote)",
        "detail_text": (
            "About the job Retail Operations Manager. Easy Apply. "
            "Lead merchandising, inventory, and omnichannel operations."
        ),
        "detail_read": True,
    }
    detailed = opportunity_from_browser_job(
        detail_payload,
        now=datetime(2026, 7, 10, 16, 30, tzinfo=UTC),
    )
    state.upsert_opportunities([detailed], db_path=db)

    card_payload = {
        **detail_payload,
        "captured_at": "2026-07-10T16:40:00+00:00",
        "location": "Retail Manager | $65/hr Remote",
        "detail_text": "",
        "snippet": "Actively reviewing applicants · Easy Apply",
        "detail_read": False,
    }
    card = opportunity_from_browser_job(
        card_payload,
        now=datetime(2026, 7, 10, 16, 40, tzinfo=UTC),
    )
    state.upsert_opportunities([card], db_path=db)

    stored = state.get_opportunity(detailed.opportunity_id, db_path=db)
    assert stored is not None
    assert stored.description == detailed.description
    assert stored.location == "European Union (Remote)"
    assert "chrome:linkedin_job_detail" in stored.evidence.source_facts
    assert stored.live_status == "live"
    assert stored.live_check_note == "browser_detail_matching_role_with_apply_signal"


def test_closed_linkedin_detail_stays_closed_after_card_refresh(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    detail_payload = {
        "source": "linkedin",
        "captured_at": "2026-07-10T16:30:00+00:00",
        "url": "https://www.linkedin.com/jobs/view/4430447179",
        "title": "Retail Manager | $65/hr Remote",
        "company": "Crossing Hurdles",
        "location": "European Union (Remote)",
        "detail_text": "About the job Retail Operations Manager.",
        "detail_live_text": (
            "Retail Manager | $65/hr Remote at Crossing Hurdles. "
            "Job ad is not active. You cannot apply to this job ad anymore."
        ),
        "detail_read": True,
    }
    detailed = opportunity_from_browser_job(
        detail_payload,
        now=datetime(2026, 7, 10, 16, 30, tzinfo=UTC),
    )
    state.upsert_opportunities([detailed], db_path=db)

    card_payload = {
        **detail_payload,
        "captured_at": "2026-07-12T16:30:00+00:00",
        "detail_text": "",
        "detail_live_text": "",
        "snippet": "Actively reviewing applicants",
        "detail_read": False,
    }
    card = opportunity_from_browser_job(
        card_payload,
        now=datetime(2026, 7, 12, 16, 30, tzinfo=UTC),
    )
    state.upsert_opportunities([card], db_path=db)

    stored = state.get_opportunity(detailed.opportunity_id, db_path=db)
    assert stored is not None
    assert stored.live_status == "closed"
    assert stored.status == OpportunityStatus.EXPIRED
    assert stored.likely_closed is True


def test_unseen_linkedin_browser_rows_become_unverified(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="old-linkedin-1",
        source_url="https://www.linkedin.com/jobs/view/1234567890",
        title="Operations Lead",
        company="Example",
        location="Vilnius",
        description="Lead customer operations.",
        live_status="live",
        live_checked_at="2026-07-10T08:00:00+00:00",
        live_check_method="linkedin_browser",
        live_check_note="browser_detail_live",
        status=OpportunityStatus.MATCHED,
    )
    state.upsert_opportunities([row], db_path=db)

    changed = state.mark_unseen_linkedin_browser_unverified(
        seen_native_source_ids=["different-linkedin-2"],
        snapshot_complete=True,
        db_path=db,
    )

    stored = state.get_opportunity(row.opportunity_id, db_path=db)
    assert changed == 1
    assert stored is not None
    assert stored.live_status == "unverified"
    assert stored.live_check_method == "linkedin_reconciliation"
    assert stored.live_check_note == "not_seen_in_latest_browser_snapshot"
    assert "needs_live_verification" in stored.evidence.risk_flags


def test_complete_empty_linkedin_snapshot_marks_eligible_rows_unverified(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="old-linkedin-empty",
        source_url="https://www.linkedin.com/jobs/view/2234567890",
        title="Customer Operations Lead",
        company="Example",
        location="Vilnius",
        description="Lead customer operations.",
        live_status="live",
        live_check_method="linkedin_browser",
        status=OpportunityStatus.MATCHED,
    )
    state.upsert_opportunities([row], db_path=db)

    changed = state.mark_unseen_linkedin_browser_unverified(
        seen_native_source_ids=[],
        snapshot_complete=True,
        db_path=db,
    )

    stored = state.get_opportunity(row.opportunity_id, db_path=db)
    assert changed == 1
    assert stored is not None
    assert stored.live_status == "unverified"


def test_incomplete_linkedin_snapshot_does_not_change_rows(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id="old-linkedin-incomplete",
        source_url="https://www.linkedin.com/jobs/view/3234567890",
        title="Operations Manager",
        company="Example",
        location="Vilnius",
        description="Lead operations.",
        live_status="live",
        live_check_method="linkedin_browser",
        status=OpportunityStatus.MATCHED,
    )
    state.upsert_opportunities([row], db_path=db)

    changed = state.mark_unseen_linkedin_browser_unverified(
        seen_native_source_ids=[],
        snapshot_complete=False,
        db_path=db,
    )

    stored = state.get_opportunity(row.opportunity_id, db_path=db)
    assert changed == 0
    assert stored is not None
    assert stored.live_status == "live"
    assert stored.live_check_method == "linkedin_browser"


def test_source_and_daily_runs_are_serializable_and_stored(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    source_run = state.record_source_run(
        source="greenhouse:example",
        status="failed",
        snapshot_type="snapshot",
        item_count=7,
        duration_ms=125,
        error="token=private-value\nrequest failed " + ("x" * 400),
        run_id="source-run-1",
        db_path=db,
    )
    saved_daily = state.save_daily_run(
        "daily-1",
        "partial",
        True,
        {"delivered": 3},
        db,
    )

    assert json.loads(json.dumps(source_run))["run_id"] == "source-run-1"
    assert "\n" not in source_run["error"]
    assert "private-value" not in source_run["error"]
    assert len(source_run["error"]) <= 240
    assert state.get_daily_run("daily-1", db_path=db) == saved_daily
    assert state.latest_daily_run(db_path=db) == saved_daily

    with pytest.raises(ValueError, match="snapshot_type"):
        state.record_source_run(
            source="greenhouse:example",
            status="ok",
            snapshot_type="full",
            item_count=0,
            duration_ms=1,
            error="",
            db_path=db,
        )


def test_delivery_claims_are_idempotent_across_same_day_runs(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    first = opportunity(native_source_id="delivery-1")
    duplicate = opportunity(
        native_source_id="delivery-1",
        source_url="https://jobs.example.com/roles/changed",
    )

    first_claim = state.claim_deliveries([first, duplicate], "run-1", db_path=db)
    same_run = state.claim_deliveries([first], "run-1", db_path=db)
    second_run = state.claim_deliveries([first], "run-2", db_path=db)

    assert [row.canonical_identity for row in first_claim] == [first.canonical_identity]
    assert same_run == []
    assert second_run == []
    with sqlite3.connect(db) as con:
        stored = con.execute(
            "SELECT run_id, canonical_identity FROM deliveries"
        ).fetchall()
    assert stored == [("run-1", first.canonical_identity)]


def test_delivery_preview_returns_undelivered_without_writing(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = opportunity(native_source_id="preview-1")

    preview = state.claim_deliveries(
        [row, row], "preview-run", preview=True, db_path=db
    )

    assert preview == [row]
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 0
    assert state.claim_deliveries([row], "real-run", db_path=db) == [row]


def test_delivery_is_never_repeated_on_a_later_date(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = opportunity(native_source_id="never-repeat-1")

    assert state.claim_deliveries([row], "run-1", db_path=db) == [row]
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE deliveries SET delivery_date = '2026-01-01' "
            "WHERE canonical_identity = ?",
            (row.canonical_identity,),
        )

    assert state.claim_deliveries([row], "run-2", db_path=db) == []


def test_url_change_with_same_native_id_updates_one_opportunity(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    first = opportunity(
        native_source_id="native-1",
        source_url="https://jobs.example.com/roles/old",
    )
    changed = opportunity(
        native_source_id="native-1",
        source_url="https://careers.example.com/jobs/new",
    )

    assert first.content_hash == changed.content_hash
    state.upsert_opportunities([first], db_path=db)
    state.upsert_opportunities([changed], db_path=db)

    stored = state.list_opportunities(db_path=db)
    assert len(stored) == 1
    assert stored[0].opportunity_id == first.opportunity_id
    assert stored[0].source_url == "https://careers.example.com/jobs/new"
    assert stored[0].canonical_identity == first.canonical_identity


def test_discovery_preserves_and_stamps_first_eligible_transition(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    initial = opportunity(native_source_id="eligibility-1")
    initial.location_eligibility = "verify_remote"
    initial.first_seen_at = "2026-06-01T08:00:00+00:00"
    state.upsert_opportunities([initial], db_path=db)

    eligible = opportunity(native_source_id="eligibility-1")
    eligible.location_eligibility = "eligible_eu_remote"
    state.upsert_opportunities([eligible], db_path=db)
    transitioned = state.get_opportunity(initial.opportunity_id, db_path=db)

    assert transitioned is not None
    assert transitioned.first_eligible_at

    rediscovered = opportunity(native_source_id="eligibility-1")
    rediscovered.location_eligibility = "eligible_eu_remote"
    state.upsert_opportunities([rediscovered], db_path=db)
    stored = state.get_opportunity(initial.opportunity_id, db_path=db)

    assert stored is not None
    assert stored.first_eligible_at == transitioned.first_eligible_at


def test_cross_source_semantic_alias_merges_within_30_days(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    board = opportunity(
        source="job-board",
        native_source_id="board-1",
        source_url="https://board.example.com/jobs/1",
    )
    company_site = opportunity(
        source="company-site",
        native_source_id="company-99",
        source_url="https://example.com/careers/99",
        description="The same vacancy from the company.",
    )

    state.upsert_opportunities([board], db_path=db)
    state.upsert_opportunities([company_site], db_path=db)

    stored = state.list_opportunities(db_path=db)
    assert len(stored) == 1
    assert stored[0].opportunity_id == board.opportunity_id
    assert stored[0].canonical_identity == board.canonical_identity


def test_same_source_new_native_id_remains_a_new_vacancy(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    old = opportunity(
        native_source_id="vacancy-1",
        source_url="https://jobs.example.com/roles/1",
    )
    new = opportunity(
        native_source_id="vacancy-2",
        source_url="https://jobs.example.com/roles/1",
    )

    state.upsert_opportunities([old], db_path=db)
    state.upsert_opportunities([new], db_path=db)

    stored = state.list_opportunities(db_path=db)
    assert len(stored) == 2
    assert {row.canonical_identity for row in stored} == {
        old.canonical_identity,
        new.canonical_identity,
    }
