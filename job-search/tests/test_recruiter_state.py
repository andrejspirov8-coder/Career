from __future__ import annotations

from pathlib import Path

import recruiter_state as rs


def test_approval_requires_exact_note_hash(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    rs.init_db(db)
    url = "https://www.linkedin.com/in/example-person/?miniProfileUrn=x"
    note = "Hi Jane, your luxury retail hiring focus stood out."

    assert not rs.approval_check(profile_url=url, note=note, db_path=db).approved
    note_hash = rs.approve_invite(
        profile_url=url,
        note=note,
        run_id="test-run",
        db_path=db,
    )

    ok = rs.approval_check(profile_url=url, note=note, db_path=db)
    assert ok.approved is True
    assert ok.note_hash == note_hash

    changed = rs.approval_check(profile_url=url, note=note + " Changed.", db_path=db)
    assert changed.approved is False
    assert changed.reason == "missing_matching_approval"


def test_mark_sent_blocks_future_approval_use(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    url = "https://www.linkedin.com/in/example-person/"
    note = "Hi Jane, your luxury retail hiring focus stood out."
    rs.approve_invite(profile_url=url, note=note, run_id="test-run", db_path=db)
    rs.mark_sent(profile_url=url, note=note, run_id="test-run", db_path=db)

    check = rs.approval_check(profile_url=url, note=note, db_path=db)
    assert check.approved is False
    assert check.reason == "already_sent"
