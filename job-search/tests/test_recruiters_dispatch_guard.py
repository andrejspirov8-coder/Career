from __future__ import annotations

from pathlib import Path

from career_job_search.recruiters.dispatch_guard import (
    is_stub_or_empty_row,
    load_already_sent_urls,
    validate_note_integrity,
)


def test_empty_row_skipped() -> None:
    row = {"profile_url": "", "name": "", "headline": "", "company": ""}
    skip, reason = is_stub_or_empty_row(row)
    assert skip
    assert reason == "empty_identity"


def test_name_present_no_skip() -> None:
    row = {
        "profile_url": "https://linkedin.com/in/real-person",
        "name": "Jane",
        "headline": "Engineer",
        "company": "Acme",
    }
    skip, _reason = is_stub_or_empty_row(row)
    assert not skip


def test_offline_stub_skipped() -> None:
    row = {
        "profile_url": "https://linkedin.com/in/real-person",
        "source_backend": "offline_stub",
        "discovery_source": "offline_stub",
        "name": "Jane",
        "headline": "Engineer",
        "company": "Acme",
    }
    skip, reason = is_stub_or_empty_row(row)
    assert skip
    assert reason == "offline_stub"


def test_stub_url_skipped() -> None:
    for stub_url in (
        "https://linkedin.com/in/sample/",
        "https://linkedin.com/in/test-user",
        "https://linkedin.com/in/demo/",
        "https://linkedin.com/in/example-user",
        "https://linkedin.com/in/jane-doe/",
    ):
        row = {
            "profile_url": stub_url,
            "name": "Jane",
            "headline": "Engineer",
            "company": "Acme",
        }
        skip, reason = is_stub_or_empty_row(row)
        assert skip
        assert reason == "stub_url", f"Expected stub_url for {stub_url}, got {reason}"


def test_validate_note_integrity_empty_fails() -> None:
    safe, reason = validate_note_integrity("")
    assert not safe
    assert reason == "empty_note"


def test_validate_note_integrity_clean_passes() -> None:
    safe, _reason = validate_note_integrity("Hi Jane, great profile!")
    assert safe


def test_validate_note_integrity_unresolved_template_fails() -> None:
    safe, reason = validate_note_integrity("Hi {first_name}, check {profile_phrase}")
    assert not safe
    assert "unresolved_template_tokens" in reason
    assert "first_name" in reason
    assert "profile_phrase" in reason


def test_validate_note_integrity_single_brace_ok() -> None:
    safe, _reason = validate_note_integrity("This is a { test")
    assert safe


def test_load_already_sent_urls_missing_csv(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.csv"
    result = load_already_sent_urls(missing)
    assert result == set()


def test_load_already_sent_urls_reads_sent(tmp_path: Path) -> None:
    csv_path = tmp_path / "recruiters.csv"
    csv_path.write_text(
        "profile_url,status\n"
        "https://linkedin.com/in/sent-person,sent\n"
        "https://linkedin.com/in/new-person,new\n"
        "https://linkedin.com/in/pending-person,PENDING\n",
        encoding="utf-8",
    )
    result = load_already_sent_urls(csv_path)
    assert len(result) == 2
    assert any("sent-person" in url for url in result)
    assert any("pending-person" in url for url in result)
    assert not any("new-person" in url for url in result)
