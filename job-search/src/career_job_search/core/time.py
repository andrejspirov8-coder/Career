"""Consistent timezone-aware timestamps."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso(*, timespec: str = "seconds") -> str:
    return utc_now().replace(microsecond=0).isoformat(timespec=timespec)
