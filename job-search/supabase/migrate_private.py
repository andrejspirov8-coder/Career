#!/usr/bin/env python3
"""Deliberately disabled placeholder for an unapproved remote migration path.

The application uses local SQLite under ``state/``.  This helper is retained as
historical evidence for the dormant Supabase migration, but it must not be used
as a runtime or deployment command.
"""

from __future__ import annotations


DISABLED_MESSAGE = (
    "Supabase persistence migration is disabled; application persistence is local SQLite."
)


def main() -> None:
    """Fail closed until a separately approved remote-persistence design exists."""
    raise SystemExit(DISABLED_MESSAGE)


if __name__ == "__main__":
    main()
