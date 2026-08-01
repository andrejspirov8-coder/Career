from __future__ import annotations

import sqlite3
from pathlib import Path

from career_job_search.recruiters.repository import (
    approval_check,
    approve_invite,
    count_by_status,
    init_db,
    latest_approval_metadata,
    mark_sent,
    record_operator_action,
    require_approvals,
    sent_profile_urls_on_local_date,
)


def _default_db(tmp_path: Path) -> Path:
    return tmp_path / "recruiter_state.sqlite3"


def test_init_db_creates_schema(tmp_path: Path) -> None:
    path = init_db(_default_db(tmp_path))
    with sqlite3.connect(str(path)) as con:
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {row[0] for row in tables}
    assert "schema_meta" in names
    assert "recruiter_profiles" in names
    assert "recruiter_decisions" in names
    assert "approval_expirations" in names
    assert "operator_actions" in names


def test_approve_invite_creates_approval(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    nh = approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Great profile",
        run_id="manual",
        db_path=db,
    )
    assert nh
    check = approval_check(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Great profile",
        db_path=db,
    )
    assert check.approved
    assert check.reason == "approved"


def test_approval_check_missing_profile_url(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    check = approval_check(profile_url="", note="Hello", db_path=db)
    assert not check.approved
    assert check.reason == "missing_profile_url"


def test_approval_check_missing_note(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    check = approval_check(
        profile_url="https://linkedin.com/in/jane-doe", note="", db_path=db
    )
    assert not check.approved
    assert check.reason == "missing_note"


def test_approval_check_already_sent(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Great fit",
        run_id="r1",
        db_path=db,
    )
    mark_sent(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Great fit",
        run_id="r1",
        db_path=db,
    )
    check = approval_check(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Great fit",
        db_path=db,
    )
    assert not check.approved
    assert check.reason == "already_sent"


def test_approval_check_expired_approval(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Testing expiry",
        run_id="r1",
        expires_at="2020-01-01T00:00:00+00:00",
        db_path=db,
    )
    check = approval_check(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Testing expiry",
        db_path=db,
    )
    assert not check.approved
    assert check.reason == "expired_approval"


def test_approval_check_no_expiry_never_expires(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="No expiry",
        run_id="r1",
        db_path=db,
    )
    check = approval_check(
        profile_url="https://linkedin.com/in/jane-doe",
        note="No expiry",
        db_path=db,
    )
    assert check.approved


def test_different_notes_require_separate_approval(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Version A",
        run_id="r1",
        db_path=db,
    )
    check_b = approval_check(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Version B",
        db_path=db,
    )
    assert not check_b.approved
    assert check_b.reason == "missing_matching_approval"


def test_require_approvals_collects_failures(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/approved",
        note="Good",
        run_id="r1",
        db_path=db,
    )
    invites = [
        ("https://linkedin.com/in/approved", "Good"),
        ("https://linkedin.com/in/missing", "Missing note"),
    ]
    failures = require_approvals(invites, db_path=db)
    assert len(failures) == 1
    assert "missing" in failures[0].profile_url


def test_mark_sent_records_decision(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Ready",
        run_id="r1",
        db_path=db,
    )
    nh = mark_sent(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Ready",
        run_id="r1",
        db_path=db,
    )
    assert nh
    with sqlite3.connect(str(db)) as con:
        rows = con.execute(
            "SELECT status FROM recruiter_decisions WHERE note_hash = ?", (nh,)
        ).fetchall()
    statuses = {row[0] for row in rows}
    assert "sent" in statuses


def test_sent_profile_urls_on_local_date(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/sent-today",
        note="Sent today",
        run_id="r1",
        db_path=db,
    )
    mark_sent(
        profile_url="https://linkedin.com/in/sent-today",
        note="Sent today",
        run_id="r1",
        db_path=db,
    )
    sent = sent_profile_urls_on_local_date(db_path=db)
    assert len(sent) >= 1
    assert any("sent-today" in url for url in sent)


def test_latest_approval_metadata(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/jane-doe",
        note="Check metadata",
        run_id="r1",
        approved_by="test_operator",
        approval_reason="manual_test",
        db_path=db,
    )
    meta = latest_approval_metadata(
        profile_url="https://linkedin.com/in/jane-doe",
        db_path=db,
    )
    assert meta["approved_by"] == "test_operator"
    assert meta["approval_reason"] == "manual_test"


def test_count_by_status(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    approve_invite(
        profile_url="https://linkedin.com/in/a",
        note="n1",
        run_id="r1",
        db_path=db,
    )
    approve_invite(
        profile_url="https://linkedin.com/in/b",
        note="n2",
        run_id="r2",
        db_path=db,
    )
    counts = count_by_status(db_path=db)
    assert counts.get("approved") == 2


def test_record_operator_action(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    result = record_operator_action(
        action_type="test_action",
        profile_url="https://linkedin.com/in/jane-doe",
        note="Test note",
        db_path=db,
    )
    assert result["action_type"] == "test_action"
    assert result["id"] >= 1


def test_approval_check_invalid_url_safe(tmp_path: Path) -> None:
    db = _default_db(tmp_path)
    check = approval_check(profile_url="not-a-url", note="Hi", db_path=db)
    assert not check.approved
    assert "profile_url" in check.reason
