from __future__ import annotations

from career_job_search.recruiters.matching import _term_in_blob  # noqa: E402


def test_term_in_blob_respects_single_token_boundaries() -> None:
    assert _term_in_blob("senior recruiter", "recruiter")
    assert not _term_in_blob("recruitment specialist", "recruiter")


def test_term_in_blob_matches_phrases() -> None:
    assert _term_in_blob("head of people and culture", "people and culture")
