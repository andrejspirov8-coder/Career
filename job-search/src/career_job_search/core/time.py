"""Consistent timezone-aware timestamps."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

VILNIUS_TIMEZONE = ZoneInfo("Europe/Vilnius")


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso(*, timespec: str = "seconds") -> str:
    return utc_now().replace(microsecond=0).isoformat(timespec=timespec)


def now_vilnius() -> datetime:
    return datetime.now(VILNIUS_TIMEZONE)


def today_vilnius() -> date:
    return now_vilnius().date()


def vilnius_now_iso(*, timespec: str = "seconds") -> str:
    return now_vilnius().replace(microsecond=0).isoformat(timespec=timespec)
