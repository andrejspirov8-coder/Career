from __future__ import annotations

import json
from pathlib import Path

import recruiter_match as rm

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "recruiters"


def _load(name: str) -> dict[str, str]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_luxury_retail_fixture_scores_as_relevant() -> None:
    row = _load("luxury_retail_high_match.json")
    result = rm.match_recruiter_profile(**row)
    meta = result["recruiter_meta"]
    rec = result["recommendation"]

    assert meta["recruiter_gate_ok"] is True
    assert rec["variant_slug"] in {"luxury-retail", "luxury-retail-lt"}
    assert float(rec["primary_score"]) >= 12.0


def test_generic_hr_fixture_does_not_beat_luxury_retail() -> None:
    row = _load("generic_hr_low_match.json")
    result = rm.match_recruiter_profile(**row)
    rec = result["recommendation"]

    assert rec["variant_slug"] != "luxury-retail" or float(rec["primary_score"]) < 12.0


def test_staffing_sales_fixture_is_flagged_as_not_sendable() -> None:
    row = _load("staffing_agency_excluded.json")
    result = rm.match_recruiter_profile(**row)
    ok, reason = rm.should_send_recruiter_connection(
        result,
        min_primary_score=12.0,
        min_margin_over_second=4.0,
        require_clear_winner=False,
        require_recruiter_gate=True,
    )

    assert ok is False
    assert reason
