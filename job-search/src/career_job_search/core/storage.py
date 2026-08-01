"""Abstract storage backend: local SQLite or remote Supabase.

Provides ``get_storage()`` which returns the configured backend based on
environment variables.  Every domain repository should import ``get_storage``
and delegate persistence through it — callers are oblivious to the backend.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_ANON_KEY_ENV = "SUPABASE_ANON_KEY"


class StorageBackend(ABC):
    """Interface that every storage backend must implement.

    Each method maps to a core CRUD operation shared across domains.
    Domain-specific backends (opportunities, recruiters, …) live in
    ``integrations/supabase/repositories/``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def is_remote(self) -> bool:
        return False

    # ── Lifecycle ────────────────────────────────────────────
    @abstractmethod
    def init(self) -> None:
        """Create tables / run migrations (idempotent)."""

    # ── Connection / client ──────────────────────────────────
    @abstractmethod
    def connect(self) -> Any:
        """Return a connection-like handle for the backend."""


class SQLiteBackend(StorageBackend):
    """Delegates to the existing SQLite-based infrastructure.

    This is the default backend — zero external dependencies, zero config.
    """

    @property
    def name(self) -> str:
        return "sqlite"

    def init(self) -> None:
        pass

    def connect(self) -> None:
        return None


class SupabaseBackend(StorageBackend):
    """Uses the Supabase Python client (postgREST) for all persistence.

    Requires ``SUPABASE_URL`` and ``SUPABASE_ANON_KEY`` environment variables.
    Import is deferred so the module is safe to import even when ``supabase``
    is not installed.
    """

    _client: Any = None

    @property
    def name(self) -> str:
        return "supabase"

    @property
    def is_remote(self) -> bool:
        return True

    def init(self) -> None:
        # Schema is applied via SQL migration (Phase 0), not at runtime.
        pass

    def connect(self) -> Any:
        if self._client is not None:
            return self._client
        from supabase import create_client

        url = os.environ[SUPABASE_URL_ENV]
        key = os.environ[SUPABASE_ANON_KEY_ENV]
        self._client = create_client(url, key)
        return self._client


_backend: StorageBackend | None = None


def _detect_backend() -> StorageBackend:
    has_supabase_env = SUPABASE_URL_ENV in os.environ and SUPABASE_ANON_KEY_ENV in os.environ
    if has_supabase_env:
        return SupabaseBackend()
    return SQLiteBackend()


def get_storage() -> StorageBackend:
    """Return the configured storage backend (cached)."""
    global _backend
    if _backend is None:
        _backend = _detect_backend()
    return _backend


def reset_storage_cache() -> None:
    """Clear the cached backend (useful in tests)."""
    global _backend
    _backend = None
