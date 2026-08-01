from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from career_job_search.api.context import current_user_id
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunitySourceKind,
    OpportunityStatus,
)
from career_job_search.opportunities.repository import (
    get_opportunity,
    list_opportunities,
    save_opportunity,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_opportunities.sqlite3"


def _make_opportunity(title: str) -> Opportunity:
    return Opportunity(
        opportunity_id=f"test_{uuid4().hex}",
        source="test",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        dedupe_key=f"dedupe_{uuid4().hex}",
        title=title,
        company="TestCo",
        location="TestCity",
        status=OpportunityStatus.NEW,
    )


class TestDataIsolation:
    def test_user_a_cannot_see_user_b_opportunity(self, tmp_db: Path) -> None:
        current_user_id.set("user_a")
        opp_a = _make_opportunity("User A Role")
        save_opportunity(opp_a, db_path=tmp_db)

        current_user_id.set("user_b")
        opp_b = _make_opportunity("User B Role")
        save_opportunity(opp_b, db_path=tmp_db)

        result_a = get_opportunity(opp_a.opportunity_id, db_path=tmp_db)
        result_b = get_opportunity(opp_b.opportunity_id, db_path=tmp_db)

        assert result_a is None, "user_b should not see user_a's opportunity"
        assert result_b is not None, "user_b should see their own opportunity"
        assert result_b.title == "User B Role"

    def test_list_opportunities_respects_user_boundary(self, tmp_db: Path) -> None:
        current_user_id.set("user_a")
        save_opportunity(_make_opportunity("A Role 1"), db_path=tmp_db)
        save_opportunity(_make_opportunity("A Role 2"), db_path=tmp_db)

        current_user_id.set("user_b")
        save_opportunity(_make_opportunity("B Role 1"), db_path=tmp_db)

        current_user_id.set("user_a")
        user_a_list = list_opportunities(db_path=tmp_db)
        assert len(user_a_list) == 2
        assert all("A Role" in opp.title for opp in user_a_list)

        current_user_id.set("user_b")
        user_b_list = list_opportunities(db_path=tmp_db)
        assert len(user_b_list) == 1
        assert user_b_list[0].title == "B Role 1"

    def test_local_user_fallback(self, tmp_db: Path) -> None:
        save_opportunity(_make_opportunity("Legacy Data"), db_path=tmp_db)

        current_user_id.set("other_user")
        items = list_opportunities(db_path=tmp_db)
        assert len(items) == 0
