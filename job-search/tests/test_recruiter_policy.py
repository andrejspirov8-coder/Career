from __future__ import annotations

from pathlib import Path

import pytest

from career_job_search.recruiters import repository as rs
from career_job_search.recruiters.policy import (
    MAX_LIVE_DISPATCH,
    can_attempt_live_dispatch,
    can_dispatch_live,
    current_send_mode,
    live_dispatch_slots_remaining,
    note_hash,
    require_live_dispatch_approvals,
    risk_stop_state,
    validate_live_dispatch_max,
)


def test_note_hash_matches_state() -> None:
    assert note_hash("hello") == rs.compute_note_hash("hello")


def test_can_dispatch_live_requires_approval(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    rs.init_db(db)
    decision = can_dispatch_live(
        profile_url="https://www.linkedin.com/in/example/",
        note="hi",
        db_path=db,
    )
    assert decision.allowed is False
    assert decision.reason == "missing_matching_approval"


def test_require_live_dispatch_approvals(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    rs.init_db(db)
    failures = require_live_dispatch_approvals(
        [("https://www.linkedin.com/in/example/", "hi")], db_path=db
    )
    assert len(failures) == 1


def test_send_mode_defaults_to_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINKEDIN_SEND_MODE", raising=False)
    assert current_send_mode() == "manual"


def test_live_dispatch_requires_explicit_maximum_of_three_or_less() -> None:
    with pytest.raises(SystemExit, match="explicit --max"):
        validate_live_dispatch_max(None, dry_run=False)
    with pytest.raises(SystemExit, match="range 1..3"):
        validate_live_dispatch_max(0, dry_run=False)
    with pytest.raises(SystemExit, match="cannot exceed 3"):
        validate_live_dispatch_max(4, dry_run=False)

    assert validate_live_dispatch_max(3, dry_run=False) == MAX_LIVE_DISPATCH
    assert validate_live_dispatch_max(None, dry_run=True) is None


def test_three_successful_sends_leave_no_slots_for_another_run() -> None:
    assert live_dispatch_slots_remaining(3, requested_max=3) == 0
    assert live_dispatch_slots_remaining(2, requested_max=3) == 1


def test_live_dispatch_blocked_in_manual_mode_even_with_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LINKEDIN_SEND_MODE", raising=False)
    db = tmp_path / "state.sqlite3"
    note = "Hi Lina, exact approved note."
    rs.approve_invite(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        run_id="test",
        db_path=db,
    )

    decision = can_attempt_live_dispatch(
        invites=[("https://www.linkedin.com/in/lina-area/", note)],
        allow_live_dispatch=True,
        db_path=db,
    )

    assert decision.allowed is False
    assert decision.reason == "manual_send_mode"


def test_cli_gated_live_dispatch_requires_ack_and_current_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINKEDIN_SEND_MODE", "cli_gated")
    db = tmp_path / "state.sqlite3"
    note = "Hi Lina, exact approved note."
    rs.approve_invite(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        run_id="test",
        db_path=db,
    )

    no_ack = can_attempt_live_dispatch(
        invites=[("https://www.linkedin.com/in/lina-area/", note)],
        allow_live_dispatch=False,
        db_path=db,
    )
    approved = can_attempt_live_dispatch(
        invites=[("https://www.linkedin.com/in/lina-area/", note)],
        allow_live_dispatch=True,
        db_path=db,
    )

    assert no_ack.allowed is False
    assert no_ack.reason == "missing_cli_acknowledgement"
    assert approved.allowed is True
    assert approved.reason == "approved"


def test_approval_expiry_invalidates_live_dispatch(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    note = "Hi Lina, exact approved note."
    rs.approve_invite(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        run_id="test",
        expires_at="2020-01-01T00:00:00+00:00",
        db_path=db,
    )

    check = rs.approval_check(
        profile_url="https://www.linkedin.com/in/lina-area/",
        note=note,
        db_path=db,
    )

    assert check.approved is False
    assert check.reason == "expired_approval"


def test_risk_stop_triggers_on_blocker_signals() -> None:
    state = risk_stop_state(
        screen_state="captcha",
        failure_rate=0.0,
        pending_invites=0,
        daily_cap_reached=False,
    )

    assert state["stopped"] is True
    assert state["reason"] == "captcha"
