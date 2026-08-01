from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from career_job_search.opportunities import orchestrator as orchestrate
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
    utc_now_iso,
)
from career_job_search.opportunities.repository import upsert_opportunities
from career_job_search.opportunities.sources import DiscoveryBatch, SourceResult


def alert_payload(message_id: str = "gmail-e2e-1") -> str:
    received_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    return json.dumps(
        {
            "message_id": message_id,
            "source": "LinkedIn",
            "received_at": received_at,
            "subject": "New Vilnius role",
            "body": "",
            "links": [
                {
                    "url": "https://www.linkedin.com/jobs/view/900001",
                    "title": "Luxury Retail Store Manager",
                    "company": "Example",
                    "location": "Vilnius",
                    "salary": "3500-4500 EUR gross",
                    "snippet": (
                        "Lead luxury premium boutique retail leadership, store manager "
                        "duties, clienteling, visual merchandising, brand standards, "
                        "high net worth private clients, personal shopping, store "
                        "opening, staff management, stock accuracy, replenishment, "
                        "conversion, and units per transaction."
                    ),
                }
            ],
        }
    )


def parse_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_alert_import_and_daily_queue_deliver_once(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    config = tmp_path / "opportunities.yaml"
    config.write_text("opportunities: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(alert_payload() + "\n"))

    imported = orchestrate.main(
        [
            "--config",
            str(config),
            "--db",
            str(db),
            "import-alerts",
            "--stdin",
        ]
    )
    import_output = parse_output(capsys)

    assert imported == 0
    assert import_output["data"]["imported"] == 1
    assert import_output["data"]["source_results"][0]["source"] == "linkedin"

    monkeypatch.setattr(
        orchestrate,
        "discover_opportunities_with_results",
        lambda _config: DiscoveryBatch(),
    )
    first = orchestrate.main(["--config", str(config), "--db", str(db), "daily-queue"])
    first_output = parse_output(capsys)
    second = orchestrate.main(["--config", str(config), "--db", str(db), "daily-queue"])
    second_output = parse_output(capsys)

    assert first == 0
    assert len(first_output["data"]["new_live_jobs"]) == 1
    assert first_output["data"]["new_live_jobs"][0]["source"] == "linkedin"
    assert first_output["data"]["new_live_jobs"][0]["salary_text"]
    assert first_output["data"]["new_live_jobs"][0]["source_url"].startswith(
        "https://www.linkedin.com/jobs/view/"
    )
    assert first_output["data"]["new_live_jobs"][0]["recommended_cv_visual_pdf"].endswith(
        ".pdf"
    )
    assert second == 0
    assert second_output["data"]["delivery_candidate_count"] == 0
    assert second_output["data"]["omitted_count"] == 0
    assert second_output["data"]["new_live_jobs"] == []


def test_partial_source_failure_returns_jobs_and_exit_two(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    config = tmp_path / "opportunities.yaml"
    config.write_text("opportunities: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(alert_payload("gmail-e2e-2")))
    assert (
        orchestrate.main(
            [
                "--config",
                str(config),
                "--db",
                str(db),
                "import-alerts",
                "--stdin",
            ]
        )
        == 0
    )
    capsys.readouterr()
    monkeypatch.setattr(
        orchestrate,
        "discover_opportunities_with_results",
        lambda _config: DiscoveryBatch(
            source_results=[
                SourceResult(
                    source="greenhouse:broken",
                    status="failed",
                    snapshot_type="snapshot",
                    item_count=0,
                    duration_ms=5,
                    complete=False,
                    error="timed out",
                )
            ]
        ),
    )

    code = orchestrate.main(["--config", str(config), "--db", str(db), "daily-queue"])
    output = parse_output(capsys)

    assert code == 2
    assert output["ok"] is True
    assert output["data"]["partial"] is True
    assert len(output["data"]["new_live_jobs"]) == 1
    assert output["data"]["source_results"][0]["status"] == "failed"


def test_preview_does_not_claim_delivery(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    config = tmp_path / "opportunities.yaml"
    config.write_text("opportunities: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(alert_payload("gmail-preview")))
    orchestrate.main(
        [
            "--config",
            str(config),
            "--db",
            str(db),
            "import-alerts",
            "--stdin",
        ]
    )
    capsys.readouterr()
    monkeypatch.setattr(
        orchestrate,
        "discover_opportunities_with_results",
        lambda _config: DiscoveryBatch(),
    )

    orchestrate.main(
        [
            "--config",
            str(config),
            "--db",
            str(db),
            "daily-queue",
            "--preview",
        ]
    )
    preview = parse_output(capsys)
    orchestrate.main(["--config", str(config), "--db", str(db), "daily-queue"])
    claimed = parse_output(capsys)

    assert len(preview["data"]["new_live_jobs"]) == 1
    assert preview["data"]["preview"] is True
    assert len(claimed["data"]["new_live_jobs"]) == 1


def test_old_currently_live_unlogged_match_is_delivered_once(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    config = tmp_path / "opportunities.yaml"
    config.write_text("opportunities: {}\n", encoding="utf-8")
    checked_at = utc_now_iso()
    row = Opportunity(
        source="greenhouse:example",
        source_kind=OpportunitySourceKind.ATS,
        source_url="https://boards.greenhouse.io/example/jobs/123",
        title="Customer Operations Manager",
        company="Example",
        location="Vilnius",
        location_eligibility="eligible_vilnius",
        description="Customer operations, service quality, KPI reporting, process improvement, and workflow documentation.",
        first_seen_at="2026-06-01T08:00:00+00:00",
        live_status="live",
        live_checked_at=checked_at,
        live_check_method="ats_feed",
        status=OpportunityStatus.MATCHED,
    )
    row.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=20,
        fit_score=20,
        cv_score=14,
        confidence="clear_winner",
        margin_over_second=6,
    )
    upsert_opportunities([row], db_path=db)
    monkeypatch.setattr(
        orchestrate,
        "discover_opportunities_with_results",
        lambda _config: DiscoveryBatch(),
    )
    monkeypatch.setattr(
        orchestrate,
        "match_opportunities",
        lambda rows, scoring_config=None: rows,
    )

    first = orchestrate.main(["--config", str(config), "--db", str(db), "daily-queue"])
    first_output = parse_output(capsys)
    second = orchestrate.main(["--config", str(config), "--db", str(db), "daily-queue"])
    second_output = parse_output(capsys)

    assert first == 0
    assert len(first_output["data"]["new_live_jobs"]) == 1
    assert first_output["data"]["new_live_jobs"][0]["source_url"].endswith("/123")
    assert second == 0
    assert second_output["data"]["new_live_jobs"] == []
    assert second_output["data"]["delivery_candidate_count"] == 0
