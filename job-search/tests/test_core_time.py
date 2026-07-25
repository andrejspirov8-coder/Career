from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from career_job_search.core.time import (
    VILNIUS_TIMEZONE,
    now_vilnius,
    today_vilnius,
    utc_now,
    utc_now_iso,
    vilnius_now_iso,
)


def test_vilnius_timezone_is_europe_vilnius():
    assert VILNIUS_TIMEZONE == ZoneInfo("Europe/Vilnius")


def test_utc_now_returns_aware_datetime():
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.tzinfo.utcoffset(now) == timezone.utc.utcoffset(now)


def test_utc_now_is_close_to_real_time():
    before = datetime.now(timezone.utc)
    now = utc_now()
    after = datetime.now(timezone.utc)
    assert before <= now <= after


def test_now_vilnius_returns_vilnius_tz():
    now = now_vilnius()
    assert now.tzinfo == VILNIUS_TIMEZONE or now.tzinfo.utcoffset(now) == VILNIUS_TIMEZONE.utcoffset(now)


def test_today_vilnius_returns_date():
    d = today_vilnius()
    assert isinstance(d, date)


def test_today_vilnius_matches_now_vilnius_date():
    assert today_vilnius() == now_vilnius().date()


def test_utc_now_iso_returns_string():
    s = utc_now_iso()
    assert isinstance(s, str)
    assert s.endswith("+00:00")


def test_utc_now_iso_timespec():
    s = utc_now_iso(timespec="minutes")
    parts = s.split("+")[0]
    assert parts.count(":") == 1


def test_vilnius_now_iso_returns_string():
    s = vilnius_now_iso()
    assert isinstance(s, str)


def test_vilnius_now_iso_contains_tz():
    s = vilnius_now_iso()
    assert "+03:00" in s or "+02:00" in s
