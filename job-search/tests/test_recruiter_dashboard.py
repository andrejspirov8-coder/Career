from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import recruiter_state as rs
from recruiter_dashboard import (
    SAFE_ACTIONS,
    approve_dashboard_note,
    build_overview,
    bulk_update_profile_status,
    mark_profile_review,
    mark_profile_skipped,
    read_dashboard_action_history,
    record_dashboard_operator_action,
    run_dashboard_action,
    update_action_plan_note,
)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_overview_reports_schema_counts_and_approval_status(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    recruiters = tmp_path / "recruiters.csv"
    state_db = tmp_path / "state.sqlite3"
    run_state = tmp_path / "hiring_network_run_state.json"
    persona_stats = tmp_path / "persona_stats.json"

    write_jsonl(
        action_plan,
        [
            {
                "profile_url": "https://www.linkedin.com/in/lina-area/",
                "name": "Lina Area",
                "headline": "Area Manager premium retail Lithuania",
                "persona": "retail_area_leader",
                "cv_variant": "luxury-retail",
                "rank_score": 88,
                "send_tier": "auto_send",
                "decision": "approved",
                "risk_flags": [],
                "note": "Hi Lina, your Area Manager work stood out.",
                "note_reason": "retail_area_leader:Area Manager:luxury-retail",
            },
            {
                "profile_url": "https://www.linkedin.com/in/jane-review/",
                "name": "Jane Review",
                "persona": "recruiter_hr",
                "cv_variant": "operations-management",
                "rank_score": 64,
                "send_tier": "queue_review",
                "decision": "review",
                "risk_flags": ["low_confidence"],
                "note": "Hi Jane, your recruiting work looked relevant.",
            },
        ],
    )
    recruiters.write_text(
        "profile_url,status,variant_slug,persona,accepted_at,reply_at,interview_at,note_preview\n"
        "https://www.linkedin.com/in/sent-one/,sent,luxury-retail,recruiter_hr,2026-05-01,,,\n",
        encoding="utf-8",
    )
    rs.approve_invite(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note="Hi Lina, your Area Manager work stood out.",
        run_id="test",
        db_path=state_db,
    )

    overview = build_overview(
        action_plan_path=action_plan,
        recruiters_csv_path=recruiters,
        state_db_path=state_db,
        run_state_path=run_state,
        persona_stats_path=persona_stats,
    )

    assert overview["schema"] == "recruiter_dashboard_overview_v1"
    assert overview["counts"]["auto_send"] == 1
    assert overview["counts"]["queue_review"] == 1
    assert overview["counts"]["approved_notes"] == 1
    assert overview["counts"]["sent"] == 1
    assert len(overview["queues"]["sent"]) == 1
    assert overview["queues"]["auto_send"][0]["approval"]["approved"] is True
    assert overview["queues"]["review"][0]["approval"]["reason"] == "missing_matching_approval"
    assert overview["metrics"]["personas"]["recruiter_hr"]["sent"] == 1
    assert overview["safe_actions"]["search_rank"] == SAFE_ACTIONS["search_rank"]


def test_overview_sent_queue_excludes_dry_run_log_rows(tmp_path: Path) -> None:
    recruiters = tmp_path / "recruiters.csv"
    recruiters.write_text(
        "profile_url,status,variant_slug,persona,accepted_at,reply_at,interview_at,note_preview\n"
        "https://www.linkedin.com/in/sent-one/,sent,luxury-retail,recruiter_hr,,,,\n"
        "https://www.linkedin.com/in/dry-run/,dry_run_would_skip,luxury-retail,recruiter_hr,,,,\n",
        encoding="utf-8",
    )

    overview = build_overview(
        action_plan_path=tmp_path / "missing.jsonl",
        recruiters_csv_path=recruiters,
        state_db_path=tmp_path / "state.sqlite3",
        run_state_path=tmp_path / "run.json",
        persona_stats_path=tmp_path / "persona.json",
    )

    assert overview["counts"]["sent"] == 1
    assert [row["profile_url"] for row in overview["queues"]["sent"]] == [
        "https://www.linkedin.com/in/sent-one/"
    ]


def test_overview_reports_active_run_and_recent_runs(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "dashboard-runs"
    runtime_dir.mkdir()
    (runtime_dir / "dashboard-action.lock").write_text(
        json.dumps({"action": "search_rank", "started_at": "2026-05-24T10:00:00+00:00"}),
        encoding="utf-8",
    )
    for index in range(6):
        (runtime_dir / f"run-20260524T10000{index}Z-preflight.json").write_text(
            json.dumps(
                {
                    "action": f"preflight-{index}",
                    "started_at": f"2026-05-24T10:00:0{index}+00:00",
                    "finished_at": f"2026-05-24T10:00:1{index}+00:00",
                    "returncode": index,
                    "stdout": "ok",
                    "stderr": "",
                }
            ),
            encoding="utf-8",
        )
    (runtime_dir / "run-malformed.json").write_text("{bad json", encoding="utf-8")

    overview = build_overview(
        action_plan_path=tmp_path / "missing.jsonl",
        recruiters_csv_path=tmp_path / "recruiters.csv",
        state_db_path=tmp_path / "state.sqlite3",
        run_state_path=tmp_path / "run.json",
        persona_stats_path=tmp_path / "persona.json",
        runtime_dir=runtime_dir,
    )

    assert overview["active_run"]["action"] == "search_rank"
    assert overview["active_run"]["started_at"] == "2026-05-24T10:00:00+00:00"
    assert len(overview["recent_runs"]) == 5
    assert overview["recent_runs"][0]["action"] == "preflight-5"
    assert all(run["action"] != "preflight-0" for run in overview["recent_runs"])


def test_run_dashboard_action_persists_recent_run_result(tmp_path: Path) -> None:
    result = run_dashboard_action(
        "preflight",
        runtime_dir=tmp_path,
        command_override=[sys.executable, "-c", "print('dashboard ok')"],
    )

    run_files = sorted(tmp_path.glob("run-*.json"))
    assert len(run_files) == 1
    saved = json.loads(run_files[0].read_text(encoding="utf-8"))
    assert result["returncode"] == 0
    assert saved["action"] == "preflight"
    assert saved["returncode"] == 0
    assert "dashboard ok" in saved["stdout"]


def test_update_action_plan_note_validates_and_rewrites_exact_profile(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    write_jsonl(
        action_plan,
        [
            {
                "profile_url": "https://www.linkedin.com/in/lina-area/",
                "note": "Hi Lina, old note.",
                "note_reason": "old",
            }
        ],
    )

    result = update_action_plan_note(
        profile_url="https://linkedin.com/in/lina-area/",
        note="Hi Lina, updated note for review.",
        action_plan_path=action_plan,
    )

    assert result["updated"] is True
    rows = [json.loads(line) for line in action_plan.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["note"] == "Hi Lina, updated note for review."
    assert rows[0]["note_reason"].endswith(":dashboard_edit")


def test_update_action_plan_note_rejects_unsafe_note(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    write_jsonl(action_plan, [{"profile_url": "https://www.linkedin.com/in/lina-area/"}])

    with pytest.raises(ValueError, match="unresolved_template_tokens"):
        update_action_plan_note(
            profile_url="https://www.linkedin.com/in/lina-area/",
            note="Hi {first_name}, this was not rendered.",
            action_plan_path=action_plan,
        )


def test_approve_dashboard_note_uses_exact_note_hash(tmp_path: Path) -> None:
    state_db = tmp_path / "state.sqlite3"
    note = "Hi Lina, exact approved note."
    result = approve_dashboard_note(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        state_db_path=state_db,
        run_id="dashboard-test",
    )

    assert result["approved"] is True
    assert rs.approval_check(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        db_path=state_db,
    ).approved
    assert not rs.approval_check(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note + " Changed.",
        db_path=state_db,
    ).approved


def test_dashboard_actions_reject_unsafe_actions_and_live_flags(tmp_path: Path) -> None:
    assert "search_rank" in SAFE_ACTIONS

    with pytest.raises(ValueError, match="Unsupported dashboard action"):
        run_dashboard_action("live_dispatch", runtime_dir=tmp_path)

    with pytest.raises(ValueError, match="Unsafe dashboard command"):
        run_dashboard_action(
            "preflight",
            runtime_dir=tmp_path,
            command_override=["python", "tools/hiring_network_workflow.py", "--allow-live-dispatch"],
        )


def test_overview_builds_saved_views_and_profile_details(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    history = tmp_path / "history.jsonl"
    state_db = tmp_path / "state.sqlite3"
    approved_note = "Hi Lina, exact approved note."
    write_jsonl(
        action_plan,
        [
            {
                "profile_url": "https://www.linkedin.com/in/lina-area/",
                "name": "Lina Area",
                "headline": "Area Manager premium retail Lithuania",
                "persona": "retail_area_leader",
                "cv_variant": "luxury-retail",
                "rank_score": 88,
                "profile_confidence": 0.93,
                "send_tier": "auto_send",
                "decision": "approved",
                "risk_flags": [],
                "note": approved_note,
                "top_signals": ["area_manager", "premium_retail"],
            },
            {
                "profile_url": "https://www.linkedin.com/in/jane-review/",
                "name": "Jane Review",
                "persona": "recruiter_hr",
                "cv_variant": "operations-management",
                "rank_score": 64,
                "send_tier": "queue_review",
                "decision": "review",
                "risk_flags": ["low_confidence"],
                "note": "Hi Jane, review note.",
            },
            {
                "profile_url": "https://www.linkedin.com/in/pat-skip/",
                "name": "Pat Skip",
                "send_tier": "skip",
                "decision": "skip",
                "risk_flags": ["staffing_agency"],
                "note": "Hi Pat, skip note.",
            },
        ],
    )
    history.write_text(
        json.dumps(
            {
                "action_type": "mark_review",
                "profile_url": "https://www.linkedin.com/in/jane-review/",
                "timestamp": "2026-05-26T10:00:00+00:00",
                "old_status": "skip:skip",
                "new_status": "queue_review:review",
                "operator_source": "dashboard",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rs.approve_invite(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=approved_note,
        run_id="test",
        db_path=state_db,
    )

    overview = build_overview(
        action_plan_path=action_plan,
        recruiters_csv_path=tmp_path / "recruiters.csv",
        state_db_path=state_db,
        run_state_path=tmp_path / "run.json",
        persona_stats_path=tmp_path / "persona.json",
        action_history_path=history,
    )

    saved = overview["queues"]["saved_views"]
    assert [row["profile_url"] for row in saved["needs_review"]] == [
        "https://www.linkedin.com/in/jane-review/"
    ]
    assert [row["profile_url"] for row in saved["auto_send_candidates"]] == [
        "https://www.linkedin.com/in/lina-area/"
    ]
    assert [row["profile_url"] for row in saved["approved"]] == [
        "https://www.linkedin.com/in/lina-area/"
    ]
    assert {row["profile_url"] for row in saved["risk_flags"]} == {
        "https://www.linkedin.com/in/jane-review/",
        "https://www.linkedin.com/in/pat-skip/",
    }
    jane = saved["needs_review"][0]
    assert jane["score_details"]["rank_score"] == 64
    assert jane["approval"]["approved"] is False
    assert jane["action_history"][0]["action_type"] == "mark_review"
    assert overview["run_history"] == overview["recent_runs"]
    assert overview["live_dispatch"]["mode"] == "manual"


def test_mark_profile_skipped_records_history_and_preserves_other_rows(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    history = tmp_path / "history.jsonl"
    write_jsonl(
        action_plan,
        [
            {
                "profile_url": "https://www.linkedin.com/in/lina-area/",
                "send_tier": "queue_review",
                "decision": "review",
            },
            {
                "profile_url": "https://www.linkedin.com/in/other/",
                "send_tier": "auto_send",
                "decision": "approved",
            },
        ],
    )

    result = mark_profile_skipped(
        profile_url="https://linkedin.com/in/lina-area/",
        action_plan_path=action_plan,
        action_history_path=history,
    )

    rows = [json.loads(line) for line in action_plan.read_text(encoding="utf-8").splitlines()]
    assert result["updated"] is True
    assert rows[0]["send_tier"] == "skip"
    assert rows[0]["decision"] == "skip"
    assert rows[1]["send_tier"] == "auto_send"
    actions = read_dashboard_action_history(history)
    assert actions[0]["action_type"] == "mark_skipped"
    assert actions[0]["old_status"] == "queue_review:review"
    assert actions[0]["new_status"] == "skip:skip"


def test_mark_profile_review_moves_skipped_profile_back_to_review(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    history = tmp_path / "history.jsonl"
    write_jsonl(
        action_plan,
        [
            {
                "profile_url": "https://www.linkedin.com/in/lina-area/",
                "send_tier": "skip",
                "decision": "skip",
            }
        ],
    )

    result = mark_profile_review(
        profile_url="https://www.linkedin.com/in/lina-area/",
        action_plan_path=action_plan,
        action_history_path=history,
    )

    rows = [json.loads(line) for line in action_plan.read_text(encoding="utf-8").splitlines()]
    assert result["updated"] is True
    assert rows[0]["send_tier"] == "queue_review"
    assert rows[0]["decision"] == "review"
    assert read_dashboard_action_history(history)[0]["action_type"] == "mark_review"


def test_bulk_status_update_rejects_bulk_approval(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    write_jsonl(
        action_plan,
        [{"profile_url": "https://www.linkedin.com/in/lina-area/"}],
    )

    with pytest.raises(ValueError, match="Bulk approval is not supported"):
        bulk_update_profile_status(
            profile_urls=["https://www.linkedin.com/in/lina-area/"],
            target_status="approved",
            action_plan_path=action_plan,
            action_history_path=tmp_path / "history.jsonl",
        )


def test_overview_exposes_human_in_loop_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINKEDIN_SEND_MODE", raising=False)
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    state_db = tmp_path / "state.sqlite3"
    note = "Hi Lina, your Area Manager work stood out."
    write_jsonl(
        action_plan,
        [
            {
                "profile_url": "https://www.linkedin.com/in/lina-area/",
                "name": "Lina Area",
                "headline": "Area Manager premium retail Lithuania",
                "company": "Apranga",
                "location": "Vilnius",
                "persona": "retail_area_leader",
                "cv_variant": "luxury-retail",
                "rank_score": 88,
                "profile_confidence": 0.93,
                "send_tier": "auto_send",
                "decision": "approved",
                "risk_flags": [],
                "note": note,
                "top_signals": ["area_manager", "premium_retail"],
            }
        ],
    )
    rs.approve_invite(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        run_id="test",
        approved_by="andrej",
        approval_reason="strong_match",
        expires_at="2099-01-01T00:00:00+00:00",
        db_path=state_db,
    )

    overview = build_overview(
        action_plan_path=action_plan,
        recruiters_csv_path=tmp_path / "recruiters.csv",
        state_db_path=state_db,
        run_state_path=tmp_path / "run.json",
        persona_stats_path=tmp_path / "persona.json",
    )

    row = overview["queues"]["auto_send"][0]
    assert overview["send_mode"] == "manual"
    assert overview["live_dispatch"]["mode"] == "manual"
    assert overview["campaign"]["readiness"]["ready_for_manual_send"] == 1
    assert overview["risk_stop_state"]["stopped"] is False
    assert row["profile_evidence"]["source"] == "action_plan"
    assert "premium_retail" in row["profile_evidence"]["cv_fit"]["evidence"]
    assert row["score_explanation"]["decision"] == "approved"
    assert row["next_action"] == "copy_note"
    assert row["note_quality"]["valid"] is True
    assert row["approval"]["approved_by"] == "andrej"
    assert row["approval"]["expires_at"] == "2099-01-01T00:00:00+00:00"


def test_dashboard_operator_action_records_copy_and_manual_sent(tmp_path: Path) -> None:
    history = tmp_path / "history.jsonl"
    state_db = tmp_path / "state.sqlite3"
    profile_url = "https://www.linkedin.com/in/lina-area/"
    note = "Hi Lina, exact approved note."

    copied = record_dashboard_operator_action(
        action_type="copy_note_recorded",
        profile_url=profile_url,
        note=note,
        action_history_path=history,
        state_db_path=state_db,
        operator_source="dashboard-test",
    )
    sent = record_dashboard_operator_action(
        action_type="mark_sent_manual",
        profile_url=profile_url,
        note=note,
        action_history_path=history,
        state_db_path=state_db,
        operator_source="dashboard-test",
    )

    actions = read_dashboard_action_history(history)
    assert copied["recorded"] is True
    assert sent["recorded"] is True
    assert [row["action_type"] for row in actions] == [
        "copy_note_recorded",
        "mark_sent_manual",
    ]
    assert rs.count_by_status(state_db)["sent"] == 1
