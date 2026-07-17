from __future__ import annotations

from pathlib import Path

from recruiter_config import load_settings


def test_load_settings_defaults_when_file_missing(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.yaml")
    assert settings.runtime.dry_run_default is True
    assert settings.runtime.require_approval_ledger is True
    assert settings.limits.max_live_dispatch_batch == 3
    assert settings.state.database_path.endswith("recruiter_state.sqlite3")
