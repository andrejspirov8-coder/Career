from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_job_search.opportunities.dashboard_adapter import (
    build_opportunity_overview,
    record_opportunity_action,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
    utc_now_iso,
)
from career_job_search.opportunities.preferences import (
    SearchPreferences,
    apply_search_preferences,
    evaluate_search_preferences,
    load_search_preferences,
    save_search_preferences,
)
from career_job_search.opportunities.repository import (
    actions_for_opportunity,
    get_opportunity,
    upsert_opportunities,
)


def test_search_preferences_save_privately_and_validate_queue_size(tmp_path: Path) -> None:
    path = tmp_path / "state" / "search_preferences.json"
    saved = save_search_preferences(
        {
            "target_roles": ["Customer Operations", "customer operations"],
            "priority_locations": ["Vilnius", "Remote EU"],
            "work_arrangements": ["hybrid", "remote_eu"],
            "minimum_salary_eur_monthly": 3000,
            "excluded_keywords": ["commission only"],
            "excluded_companies": ["Example Corp"],
            "daily_queue_size": 8,
        },
        path=path,
    )

    assert saved.target_roles == ["Customer Operations"]
    assert load_search_preferences(path).daily_queue_size == 8
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8"))["updated_at"]

    with pytest.raises(ValidationError):
        save_search_preferences(
            {**saved.model_dump(by_alias=True), "daily_queue_size": 11},
            path=path,
        )


def test_search_preferences_influence_discovery_config_without_mutating_input() -> None:
    config = {
        "opportunities": {
            "scoring": {"role_tracks": [{"name": "existing", "keywords": ["ops"]}]},
            "sources": {"linkedin": {"queries": ["old query"]}},
        }
    }
    preferences = SearchPreferences(
        target_roles=["Customer Operations", "Implementation Manager"],
        priority_locations=["Vilnius", "Remote EU"],
    )

    updated = apply_search_preferences(config, preferences)

    assert config["opportunities"]["sources"]["linkedin"]["queries"] == ["old query"]
    assert updated["opportunities"]["sources"]["linkedin"]["queries"] == [
        "Customer Operations",
        "Implementation Manager",
    ]
    assert updated["opportunities"]["scoring"]["priority_regions"] == [
        "Vilnius",
        "Remote EU",
    ]
    assert updated["opportunities"]["scoring"]["role_tracks"][-1]["name"] == (
        "user_search_profile"
    )


def _queue_role(index: int) -> Opportunity:
    row = Opportunity(
        opportunity_id=f"opp_queue_{index}",
        source="greenhouse:example",
        source_kind=OpportunitySourceKind.ATS,
        source_url=f"https://example.com/jobs/{index}",
        title=f"Customer Operations Manager {index}",
        company=f"Example {index}",
        location="Vilnius",
        remote_policy="hybrid",
        description="Customer operations, workflow, quality, and stakeholder leadership.",
        status=OpportunityStatus.MATCHED,
    )
    row.location_eligibility = "eligible_vilnius"
    row.match = OpportunityMatch(
        best_variant="business-process-operations",
        score=30 - index,
        fit_score=30 - index,
        cv_score=20 - index / 10,
        role_track="customer_operations",
        confidence="clear_winner",
        margin_over_second=6,
    )
    row.live_status = "live"
    row.live_checked_at = utc_now_iso()
    row.live_check_method = "test"
    row.next_action = "review"
    return row


def test_daily_queue_obeys_saved_size_and_explicit_exclusions(tmp_path: Path) -> None:
    db = tmp_path / "opportunities.sqlite3"
    rows = [_queue_role(index) for index in range(9)]
    rows[0].company = "Blocked Company"
    upsert_opportunities(rows, db_path=db)
    preferences = SearchPreferences(
        target_roles=["customer operations"],
        priority_locations=["Vilnius"],
        work_arrangements=["hybrid"],
        excluded_companies=["Blocked Company"],
        daily_queue_size=7,
    )

    overview = build_opportunity_overview(
        db_path=db,
        search_preferences=preferences,
    )

    daily_queue = overview["queues"]["saved_views"]["daily_queue"]
    assert len(daily_queue) == 7
    assert "opp_queue_0" not in daily_queue
    assert overview["counts"]["daily_queue"] == 7
    assert overview["search_profile"]["daily_queue_size"] == 7
    summary = next(
        row for row in overview["queues"]["all"] if row["opportunity_id"] == "opp_queue_1"
    )
    assert summary["preference"]["reasons"][0].startswith("Matches your target role")


def test_skip_reason_suggestion_and_safe_undo_use_existing_action_history(
    tmp_path: Path,
) -> None:
    db = tmp_path / "opportunities.sqlite3"
    row = _queue_role(1)
    upsert_opportunities([row], db_path=db)

    skipped = record_opportunity_action(
        action_type="mark_skipped",
        opportunity_id=row.opportunity_id,
        db_path=db,
        decision_reason="company",
        decision_note="Not a company I want to target.",
        operator_source="test",
    )

    assert skipped["can_undo"] is True
    assert skipped["preference_suggestion"] == {
        "kind": "add_excluded_company",
        "value": "Example 1",
        "label": "Exclude Example 1 from future daily queues",
    }
    history = actions_for_opportunity(row.opportunity_id, db_path=db)
    assert history[0]["metadata"]["decision_reason"] == "company"

    undone = record_opportunity_action(
        action_type="undo_last_decision",
        opportunity_id=row.opportunity_id,
        db_path=db,
        operator_source="test",
    )
    restored = get_opportunity(row.opportunity_id, db_path=db)
    assert undone["undone_action"] == "mark_skipped"
    assert restored is not None
    assert restored.status == OpportunityStatus.MATCHED


def test_explicit_exclusions_are_hard_but_unknown_salary_is_not() -> None:
    row = _queue_role(2).to_json_dict()
    preferences = SearchPreferences(
        excluded_keywords=["stakeholder leadership"],
        minimum_salary_eur_monthly=5000,
    )
    evaluation = evaluate_search_preferences(row, preferences)
    assert evaluation["eligible"] is False
    assert "excluded_keyword" in evaluation["flags"]
    assert "salary_below_minimum" not in evaluation["flags"]
