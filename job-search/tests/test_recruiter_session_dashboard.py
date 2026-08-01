from __future__ import annotations

import json
from pathlib import Path

from career_job_search.recruiters.dashboard_adapter import (
    build_overview,
    bulk_update_profile_status,
    update_action_plan_note,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def session_row(
    *,
    profile_url: str = "https://www.linkedin.com/in/jane-recruiter/",
    headline: str = "Talent Partner at Hiring Now UAB",
) -> dict[str, object]:
    return {
        "profile_url": profile_url,
        "name": "Jane Recruiter",
        "headline": headline,
        "primary_score": 82,
        "variant_slug_best": "operations-management",
        "note_live_full": "Hi Jane, your work at Hiring Now UAB stood out.",
        "target_company": "Hiring Now UAB",
        "target_opportunity_id": "opp-123",
        "target_role_title": "Operations Manager",
        "target_company_verified": True,
    }


def write_session(path: Path, rows: list[dict[str, object]]) -> None:
    write_json(
        path,
        {
            "schema": "recruiter_session_state_v1",
            "generated_at": "2026-07-24T08:00:00+00:00",
            "queue": rows,
        },
    )


def test_overview_includes_safe_session_queue_for_manual_review(
    tmp_path: Path,
) -> None:
    session = tmp_path / "recruiter_session_state.json"
    write_session(
        session,
        [
            session_row(),
            session_row(
                profile_url="https://www.linkedin.com/in/alex-contact/",
                headline="Business Analyst at Hiring Now UAB — OOO until August",
            ),
        ],
    )

    overview = build_overview(
        action_plan_path=tmp_path / "hiring_network_action_plan.jsonl",
        session_state_path=session,
        recruiters_csv_path=tmp_path / "recruiters.csv",
        state_db_path=tmp_path / "state.sqlite3",
        run_state_path=tmp_path / "run.json",
        persona_stats_path=tmp_path / "persona.json",
    )

    assert overview["counts"]["total_ranked"] == 2
    assert overview["counts"]["session_queue"] == 2
    assert overview["counts"]["queue_review"] == 2
    jane, alex = overview["queues"]["review"]
    assert jane["source_backend"] == "linkedin_session_queue"
    assert jane["persona"] == "recruiter_hr"
    assert jane["target_company"] == "Hiring Now UAB"
    assert jane["target_company_verified"] is True
    assert jane["cv_variant"] == "operations-management"
    assert jane["next_action"] == "approve_note"
    assert set(alex["risk_flags"]) == {
        "hiring_authority_unverified",
        "out_of_office",
    }
    assert alex["next_action"] == "review"


def test_explicit_dashboard_decision_wins_over_session_queue(tmp_path: Path) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    action_plan.write_text(
        json.dumps(
            {
                "profile_url": "https://www.linkedin.com/in/jane-recruiter/",
                "send_tier": "skip",
                "decision": "skip",
                "note": "Hi Jane, saved dashboard note.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    write_session(
        tmp_path / "recruiter_session_state.json",
        [session_row()],
    )

    overview = build_overview(
        action_plan_path=action_plan,
        recruiters_csv_path=tmp_path / "recruiters.csv",
        state_db_path=tmp_path / "state.sqlite3",
        run_state_path=tmp_path / "run.json",
        persona_stats_path=tmp_path / "persona.json",
    )

    assert overview["counts"]["total_ranked"] == 1
    assert overview["counts"]["session_queue"] == 0
    assert overview["counts"]["skipped"] == 1
    assert overview["queues"]["skipped"][0]["note"] == "Hi Jane, saved dashboard note."


def test_note_edit_materializes_session_profile_before_update(
    tmp_path: Path,
) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    session = tmp_path / "recruiter_session_state.json"
    write_session(session, [session_row()])

    result = update_action_plan_note(
        profile_url="https://linkedin.com/in/jane-recruiter/",
        note="Hi Jane, I am interested in the open operations role.",
        action_plan_path=action_plan,
        session_state_path=session,
        action_history_path=tmp_path / "history.jsonl",
    )

    saved = json.loads(action_plan.read_text(encoding="utf-8").strip())
    assert result["updated"] is True
    assert saved["profile_url"] == "https://www.linkedin.com/in/jane-recruiter/"
    assert saved["note"] == "Hi Jane, I am interested in the open operations role."
    assert saved["send_tier"] == "queue_review"


def test_bulk_status_change_materializes_only_requested_session_profiles(
    tmp_path: Path,
) -> None:
    action_plan = tmp_path / "hiring_network_action_plan.jsonl"
    session = tmp_path / "recruiter_session_state.json"
    write_session(
        session,
        [
            session_row(),
            session_row(profile_url="https://www.linkedin.com/in/other-contact/"),
        ],
    )

    result = bulk_update_profile_status(
        profile_urls=["https://linkedin.com/in/jane-recruiter/"],
        target_status="skipped",
        action_plan_path=action_plan,
        session_state_path=session,
        action_history_path=tmp_path / "history.jsonl",
    )

    saved = [
        json.loads(line)
        for line in action_plan.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert result["updated_count"] == 1
    assert len(saved) == 1
    assert saved[0]["profile_url"] == "https://www.linkedin.com/in/jane-recruiter/"
    assert saved[0]["send_tier"] == "skip"
    assert saved[0]["decision"] == "skip"
