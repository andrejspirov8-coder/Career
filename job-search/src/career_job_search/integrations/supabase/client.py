"""Supabase client singleton for the career project.

All tables live in the ``public`` schema (the default).  Repository code uses
bare table names (e.g. ``client.table("opportunities")``).
"""

from __future__ import annotations

from typing import Any

_client: Any = None


def get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    import os

    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    _client = create_client(url, key)
    return _client
