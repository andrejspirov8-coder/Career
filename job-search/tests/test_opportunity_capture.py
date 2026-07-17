from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from opportunity_capture import OpportunityCaptureInput, capture_opportunity
from opportunity_state import actions_for_opportunity, list_opportunities
from search_preferences import SearchPreferences


def test_url_capture_is_local_unverified_and_deduplicated(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    payload = {
        "url": "https://careers.example.com/jobs/customer-operations-manager?utm=chat",
        "text": "",
        "title": "Customer Operations Manager",
        "company": "Example",
        "location": "Vilnius",
    }

    first = capture_opportunity(
        payload,
        db_path=db,
        search_preferences=SearchPreferences(),
    )
    second = capture_opportunity(
        payload,
        db_path=db,
        search_preferences=SearchPreferences(),
    )

    assert first["fetched_url"] is False
    assert first["live_status"] == "unverified"
    assert second["opportunity_id"] == first["opportunity_id"]
    rows = list_opportunities(db_path=db)
    assert len(rows) == 1
    assert "needs_live_verification" in rows[0].evidence.risk_flags
    assert actions_for_opportunity(rows[0].opportunity_id, db_path=db)[0][
        "action_type"
    ] == "capture_manual"


def test_structured_text_capture_keeps_header_fields_and_body(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    result = capture_opportunity(
        {
            "url": "",
            "text": (
                "TITLE: Retail Operations Lead\n"
                "COMPANY: Example Retail\n"
                "URL: https://jobs.example.com/retail-lead\n"
                "SOURCE: referral\n"
                "---\n"
                "Lead store operations and inventory in Vilnius."
            ),
            "title": "",
            "company": "",
            "location": "",
        },
        db_path=db,
        search_preferences=SearchPreferences(),
    )

    row = list_opportunities(db_path=db)[0]
    assert result["title"] == "Retail Operations Lead"
    assert row.company == "Example Retail"
    assert row.location == "Vilnius"
    assert row.description == "Lead store operations and inventory in Vilnius."


def test_plain_text_with_colons_is_not_mistaken_for_header_format(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    text = "Customer Operations Manager\nResponsibilities: lead service quality."
    capture_opportunity(
        {"text": text, "url": "", "title": "", "company": "", "location": ""},
        db_path=db,
        search_preferences=SearchPreferences(),
    )
    assert list_opportunities(db_path=db)[0].description == text


def test_capture_rejects_credentials_and_empty_content() -> None:
    with pytest.raises(ValidationError):
        OpportunityCaptureInput(url="https://user:pass@jobs.example/1")
    with pytest.raises(ValidationError):
        OpportunityCaptureInput()
