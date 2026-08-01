from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from career_job_search.opportunities import orchestrator as orchestrate
from career_job_search.opportunities.browser import (
    BrowserJobPayloadError,
    canonical_linkedin_job_url,
    load_browser_job_payloads,
    opportunity_from_browser_job,
)
from career_job_search.opportunities.models import OpportunitySourceKind

NOW = datetime(2026, 7, 10, 16, 30, tzinfo=UTC)


def browser_payload() -> dict[str, object]:
    return {
        "source": "linkedin",
        "captured_at": NOW.isoformat(),
        "url": "https://www.linkedin.com/jobs/view/4438191493/?trk=search",
        "title": "Partner Performance Specialist, CS Operations",
        "company": "Vinted",
        "location": "Vilnius, Vilniaus, Lithuania (Hybrid)",
        "snippet": (
            "Own partner performance metrics, continuous improvement, service-level "
            "agreements, stakeholder coordination, and process-improvement projects."
        ),
        "detail_read": True,
    }


def test_browser_job_normalizes_listing_and_marks_current_live() -> None:
    row = opportunity_from_browser_job(browser_payload(), now=NOW)

    assert row.source == "linkedin"
    assert row.source_kind == OpportunitySourceKind.JOB_BOARD
    assert row.native_source_id == "4438191493"
    assert row.source_url == "https://www.linkedin.com/jobs/view/4438191493"
    assert row.location_eligibility == ""
    assert row.live_status == "live"
    assert row.live_check_method == "linkedin_browser"
    assert row.live_check_note == "browser_job_card_and_detail"
    assert "chrome:linkedin_job_detail" in row.evidence.source_facts
    assert row.evidence.confidence == 0.85


def test_old_browser_capture_requires_live_verification() -> None:
    payload = browser_payload()
    payload["captured_at"] = (NOW - timedelta(days=2)).isoformat()

    row = opportunity_from_browser_job(payload, now=NOW)

    assert row.live_status == "unverified"
    assert row.live_check_note == "browser_capture_is_old"
    assert "needs_live_verification" in row.evidence.risk_flags


def test_detail_text_can_mark_a_listing_closed() -> None:
    payload = browser_payload()
    payload["snippet"] = ""
    payload["detail_text"] = (
        "Partner Performance Specialist, CS Operations at Vinted. "
        "Job ad is not active. You cannot apply to this job ad anymore."
    )

    row = opportunity_from_browser_job(payload, now=NOW)

    assert row.live_status == "closed"
    assert row.live_check_note == "browser_detail_closed_or_inactive_text_found"
    assert row.status.value == "expired"
    assert row.likely_closed is True
    assert "likely_closed" in row.evidence.risk_flags


def test_detail_live_text_can_confirm_apply_signal_separately() -> None:
    payload = browser_payload()
    payload["detail_text"] = "About the job: Own partner performance metrics."
    payload["detail_live_text"] = (
        "Partner Performance Specialist, CS Operations at Vinted. "
        "Apply on company website. About the job: Own partner performance metrics."
    )

    row = opportunity_from_browser_job(payload, now=NOW)

    assert row.live_status == "live"
    assert row.live_check_note == "browser_detail_matching_role_with_apply_signal"


def test_browser_payload_rejects_non_linkedin_listing() -> None:
    payload = browser_payload()
    payload["url"] = "https://example.com/jobs/1"

    with pytest.raises(BrowserJobPayloadError, match="LinkedIn"):
        opportunity_from_browser_job(payload, now=NOW)


def test_browser_url_canonicalization_drops_tracking() -> None:
    assert canonical_linkedin_job_url(
        "https://uk.linkedin.com/jobs/view/123/?trackingId=private"
    ) == "https://uk.linkedin.com/jobs/view/123"


def test_browser_payload_loader_reads_ndjson() -> None:
    loaded = load_browser_job_payloads(io.StringIO(json.dumps(browser_payload()) + "\n"))

    assert len(loaded) == 1
    assert loaded[0]["title"] == "Partner Performance Specialist, CS Operations"


def test_import_browser_command_persists_source_and_listing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(browser_payload()) + "\n"))

    code = orchestrate.main(
        ["--db", str(db), "import-browser", "--stdin"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["data"]["imported"] == 1
    assert output["data"]["persisted"] == 1
    assert output["data"]["source_results"][0]["source"] == "linkedin:browser"
