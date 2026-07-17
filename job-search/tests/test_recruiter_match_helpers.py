from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from recruiter_match import _term_in_blob  # noqa: E402


def test_term_in_blob_respects_single_token_boundaries() -> None:
    assert _term_in_blob("senior recruiter", "recruiter")
    assert not _term_in_blob("recruitment specialist", "recruiter")


def test_term_in_blob_matches_phrases() -> None:
    assert _term_in_blob("head of people and culture", "people and culture")
