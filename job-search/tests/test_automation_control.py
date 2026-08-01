from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

from career_job_search.automation import control as automation
from career_job_search.opportunities.orchestrator import apply_daily_source_policy


def test_enqueue_deduplicates_active_runs(tmp_path):
    db_path = tmp_path / "automation.sqlite3"

    first, first_created = automation.enqueue_run(
        automation.RUN_KIND_DAILY_SEARCH, db_path=db_path
    )
    second, second_created = automation.enqueue_run(
        automation.RUN_KIND_DAILY_SEARCH, db_path=db_path
    )

    assert first_created is True
    assert second_created is False
    assert second["run_id"] == first["run_id"]
    assert second["status"] == "queued"


def test_schedule_enqueues_once_after_local_due_time(tmp_path):
    db_path = tmp_path / "automation.sqlite3"
    automation.update_schedule(
        enabled=True,
        schedule_time="08:00",
        timezone_name="Europe/Vilnius",
        db_path=db_path,
    )

    before, before_created = automation.enqueue_due_schedule(
        db_path=db_path,
        now=datetime(2026, 7, 13, 4, 30, tzinfo=UTC),
    )
    first, first_created = automation.enqueue_due_schedule(
        db_path=db_path,
        now=datetime(2026, 7, 13, 6, 30, tzinfo=UTC),
    )
    second, second_created = automation.enqueue_due_schedule(
        db_path=db_path,
        now=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
    )

    assert before is None
    assert before_created is False
    assert first_created is True
    assert first is not None
    assert first["trigger_source"] == "schedule_catch_up"
    assert first["scheduled_for"] == "2026-07-13T05:00:00+00:00"
    assert second_created is False
    assert second is not None
    assert second["run_id"] == first["run_id"]


def test_schedule_uses_regular_trigger_within_grace_period(tmp_path):
    db_path = tmp_path / "automation.sqlite3"
    automation.update_schedule(
        enabled=True,
        schedule_time="08:00",
        timezone_name="Europe/Vilnius",
        db_path=db_path,
    )

    run, created = automation.enqueue_due_schedule(
        db_path=db_path,
        now=datetime(2026, 7, 13, 5, 5, tzinfo=UTC),
    )

    assert created is True
    assert run is not None
    assert run["trigger_source"] == "schedule"


def test_worker_executes_fixed_daily_search_and_records_result(tmp_path, monkeypatch):
    db_path = tmp_path / "automation.sqlite3"
    log_dir = tmp_path / "logs"
    payload = {
        "ok": True,
        "data": {
            "partial": False,
            "shown_count": 1,
            "new_live_jobs": [
                {
                    "opportunity_id": "opp_1",
                    "title": "Operations Manager",
                    "company": "Example",
                }
            ],
        },
    }
    monkeypatch.setattr(
        automation,
        "command_for_kind",
        lambda _kind: (
            [
                sys.executable,
                "-c",
                f"import json; print(json.dumps({payload!r}))",
            ],
            10,
        ),
    )

    queued, _ = automation.enqueue_run(
        automation.RUN_KIND_DAILY_SEARCH, db_path=db_path
    )
    claimed = automation._claim_next_run(db_path=db_path)
    assert claimed is not None
    assert claimed["run_id"] == queued["run_id"]

    completed = automation.execute_run(claimed, db_path=db_path, log_dir=log_dir)

    assert completed["status"] == "succeeded"
    assert completed["progress"] == 100
    assert completed["result"]["shown_count"] == 1
    assert completed["result"]["new_live_jobs"][0]["company"] == "Example"


def test_daily_result_parses_stdout_only_when_stderr_has_warnings():
    status, result, error = automation._result_from_process(
        kind=automation.RUN_KIND_DAILY_SEARCH,
        returncode=0,
        stdout='{"ok": true, "data": {"shown_count": 2}}',
        stderr="A source emitted a harmless warning.\n",
    )

    assert status == "succeeded"
    assert result == {"shown_count": 2}
    assert error == ""


def test_daily_result_keeps_clear_helper_failure():
    status, result, error = automation._result_from_process(
        kind=automation.RUN_KIND_DAILY_SEARCH,
        returncode=1,
        stdout='{"ok": false, "error": "Explicit config file is missing."}',
        stderr="",
    )

    assert status == "failed"
    assert result == {}
    assert error == "Explicit config file is missing."


def test_source_health_reports_failures_without_raw_stderr():
    runs = [
        {
            "kind": automation.RUN_KIND_DAILY_SEARCH,
            "requested_at": "2026-07-15T06:00:00+00:00",
            "finished_at": "2026-07-15T06:01:00+00:00",
            "result": {
                "source_results": [
                    {
                        "source": "inbox",
                        "status": "success",
                        "complete": True,
                        "item_count": 2,
                        "duration_ms": 10,
                        "error": "must not be exposed",
                    },
                    {
                        "source": "ats",
                        "status": "failed",
                        "complete": False,
                        "item_count": 0,
                        "duration_ms": 20,
                        "error": "private raw failure",
                    },
                ],
                "source_issues": [
                    {
                        "source": "ats",
                        "kind": "failed",
                        "message": "The configured source was unavailable.",
                    }
                ],
            },
        }
    ]

    health = automation._source_health(
        runs, now=datetime(2026, 7, 15, 7, 0, tzinfo=UTC)
    )

    assert health["overall_status"] == "failed"
    assert health["sources"][0]["status"] == "healthy"
    assert health["sources"][1]["message"] == "The configured source was unavailable."
    assert "private raw failure" not in str(health)


def test_source_health_marks_old_success_as_stale():
    runs = [
        {
            "kind": automation.RUN_KIND_DAILY_SEARCH,
            "requested_at": "2026-07-13T06:00:00+00:00",
            "result": {
                "source_results": [
                    {
                        "source": "inbox",
                        "status": "success",
                        "complete": True,
                        "item_count": 0,
                        "duration_ms": 4,
                    }
                ]
            },
        }
    ]

    health = automation._source_health(
        runs, now=datetime(2026, 7, 15, 7, 0, tzinfo=UTC)
    )

    assert health["overall_status"] == "stale"
    assert health["age_hours"] == 49


def test_source_health_has_a_clear_first_run_state():
    health = automation._source_health([])

    assert health["overall_status"] == "not_run"
    assert health["sources"] == []


def test_only_one_worker_can_claim_a_queued_run(tmp_path):
    db_path = tmp_path / "automation.sqlite3"
    queued, _ = automation.enqueue_run(
        automation.RUN_KIND_DAILY_SEARCH, db_path=db_path
    )

    first = automation._claim_next_run(db_path=db_path, worker_pid=101)
    second = automation._claim_next_run(db_path=db_path, worker_pid=202)

    assert first is not None
    assert first["run_id"] == queued["run_id"]
    assert second is None


def test_cancel_and_retry_preserve_audit_link(tmp_path):
    db_path = tmp_path / "automation.sqlite3"
    queued, _ = automation.enqueue_run(automation.RUN_KIND_CV_BUILD, db_path=db_path)

    cancelled = automation.cancel_run(queued["run_id"], db_path=db_path)
    retried, created = automation.retry_run(queued["run_id"], db_path=db_path)

    assert cancelled["status"] == "cancelled"
    assert created is True
    assert retried["status"] == "queued"
    assert retried["parent_run_id"] == queued["run_id"]
    assert retried["attempt"] == 2


def test_overview_declares_linkedin_safety_boundary(tmp_path):
    overview = automation.build_overview(db_path=tmp_path / "automation.sqlite3")

    assert overview["safety"]["scheduled_linkedin_enabled"] is False
    assert overview["safety"]["live_linkedin_dispatch_enabled"] is False
    assert overview["available_actions"] == ["daily_search", "cv_build"]


def test_daily_command_uses_non_linkedin_source_policy():
    command, _timeout = automation.command_for_kind(automation.RUN_KIND_DAILY_SEARCH)

    assert "--exclude-linkedin" in command
    assert "--allow-live-dispatch" not in command


def test_daily_source_policy_disables_linkedin_without_changing_other_sources():
    config = {
        "opportunities": {
            "sources": {
                "linkedin": {"enabled": True, "mode": "connected_chrome"},
                "ats": {"enabled": True},
            }
        }
    }

    result = apply_daily_source_policy(config, exclude_linkedin=True)

    assert result["opportunities"]["sources"]["linkedin"]["enabled"] is False
    assert result["opportunities"]["sources"]["ats"]["enabled"] is True


@pytest.mark.parametrize("value", ["8:00", "24:00", "08:60", "tomorrow"])
def test_schedule_rejects_invalid_times(value):
    with pytest.raises(ValueError, match="HH:MM"):
        automation.validate_schedule_time(value)


def test_run_id_validation_rejects_path_or_shell_input():
    with pytest.raises(ValueError, match="Invalid automation run id"):
        automation.validate_run_id("../../state/opportunities.sqlite3")
    with pytest.raises(ValueError, match="Invalid automation run id"):
        automation.validate_run_id("run_123; echo unsafe")
