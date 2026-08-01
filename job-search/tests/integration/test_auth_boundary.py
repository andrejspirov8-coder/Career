# tests/integration/test_auth_boundary.py
from __future__ import annotations

from pathlib import Path

import pytest


def test_recruiter_approval_gate(tmp_path: Path):
    """Test the recruiter approval gate logic."""
    from career_job_search.recruiters.policy import can_attempt_live_dispatch
    from career_job_search.recruiters.repository import init_db, require_approvals

    db_path = tmp_path / "test_state.sqlite3"
    init_db(db_path)

    profile_url = "https://www.linkedin.com/in/test-user/"
    note = "Hello, this is a test note."

    # Add approval
    from career_job_search.recruiters.repository import approve_invite

    approve_invite(
        profile_url=profile_url,
        note=note,
        run_id="test",
        db_path=db_path,
    )

    # Test approval gate with valid approval
    invite_notes = [(profile_url, note)]
    gate = can_attempt_live_dispatch(
        invite_notes,
        allow_live_dispatch=True,
        db_path=db_path,
        send_mode="cli_gated",
    )
    assert gate.allowed is True

    # Verify approval is required and passes
    failures = require_approvals(invite_notes, db_path=db_path)
    assert len(failures) == 0

    # Test that approval fails with different note
    failures = require_approvals([(profile_url, "Different note")], db_path=db_path)
    assert len(failures) == 1
    assert failures[0].approved is False


def test_send_mode_blocks_manual_dispatch(tmp_path: Path):
    """Test that manual send mode blocks live dispatch."""
    from career_job_search.recruiters.policy import can_attempt_live_dispatch

    db_path = tmp_path / "test_state.sqlite3"
    from career_job_search.recruiters.repository import init_db

    init_db(db_path)

    profile_url = "https://www.linkedin.com/in/test-user/"
    note = "Hello, this is a test note."

    # Add approval
    from career_job_search.recruiters.repository import approve_invite

    approve_invite(
        profile_url=profile_url,
        note=note,
        run_id="test",
        db_path=db_path,
    )

    # Manual mode should block even with approval
    gate = can_attempt_live_dispatch(
        [(profile_url, note)],
        allow_live_dispatch=True,
        db_path=db_path,
        send_mode="manual",
    )
    assert gate.allowed is False
    assert gate.reason == "manual_send_mode"


def test_dispatch_limit_enforced():
    """Test that dispatch limit is enforced."""
    from career_job_search.recruiters.policy import (
        MAX_LIVE_DISPATCH,
        validate_live_dispatch_max,
    )

    # Valid max
    assert (
        validate_live_dispatch_max(3, dry_run=False, option_name="--max")
        == MAX_LIVE_DISPATCH
    )

    # Dry run allows None
    assert validate_live_dispatch_max(None, dry_run=True, option_name="--max") is None

    # Invalid values
    with pytest.raises(SystemExit, match="explicit --max"):
        validate_live_dispatch_max(None, dry_run=False, option_name="--max")

    with pytest.raises(SystemExit, match="range 1..3"):
        validate_live_dispatch_max(0, dry_run=False, option_name="--max")

    with pytest.raises(SystemExit, match="cannot exceed 3"):
        validate_live_dispatch_max(4, dry_run=False, option_name="--max")
