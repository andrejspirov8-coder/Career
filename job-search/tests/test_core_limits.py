from __future__ import annotations

from career_job_search.core.limits import MAX_LIVE_DISPATCH


def test_max_live_dispatch_is_three():
    assert MAX_LIVE_DISPATCH == 3


def test_max_live_dispatch_is_int():
    assert isinstance(MAX_LIVE_DISPATCH, int)


def test_max_live_dispatch_positive():
    assert MAX_LIVE_DISPATCH > 0
