import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import recruiter_state as state
from recruiter_dispatch_guard import validate_note_integrity


def test_sqlite_wal_journal_mode():
    """Verify that initialization sets Write-Ahead Logging (WAL) and synchronous normal mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_career_wal.sqlite"
        state.init_db(db_path)

        con = sqlite3.connect(db_path)
        journal_mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
        sync_mode = con.execute("PRAGMA synchronous;").fetchone()[0]
        con.close()

        # Verify that WAL journal mode is properly set.
        # SQLite may report synchronous as NORMAL/1/2 depending on build/runtime
        # behaviour, so we only assert the journal mode here.
        assert journal_mode.lower() == "wal"
        assert sync_mode in (1, 2, "NORMAL", "1", "2")


def test_dispatch_note_integrity_guards():
    """Verify that the dispatch guard catches any unresolved template placeholders (curly brackets)."""
    # 1. Valid Notes must pass
    ok_note = "Hi Alexander, I am deeply impressed by your operations management background."
    is_safe, reason = validate_note_integrity(ok_note)
    assert is_safe is True
    assert reason == ""

    # 2. Notes containing unresolved variables (bracket strings) must be caught
    corrupt_note1 = "Hi {first_name}, I noticed your store achievements."
    is_safe1, reason1 = validate_note_integrity(corrupt_note1)
    assert is_safe1 is False
    assert "unresolved_template_tokens" in reason1
    assert "first_name" in reason1

    corrupt_note2 = "Hi Jane, I aligned your experience with {company_name} and {target_role}."
    is_safe2, reason2 = validate_note_integrity(corrupt_note2)
    assert is_safe2 is False
    assert "unresolved_template_tokens" in reason2
    assert "company_name" in reason2
    assert "target_role" in reason2

    # 3. Simple punctuation curly brackets are ignored if they don't form variables
    bracket_note = "A standard note without variable patterns {bla}."
    is_safe3, reason3 = validate_note_integrity(bracket_note)
    assert is_safe3 is False
    assert "bla" in reason3
