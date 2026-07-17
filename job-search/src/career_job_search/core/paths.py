"""Portable paths for the installed source-tree package."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT_ENV = "CAREER_JOB_SEARCH_ROOT"
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]


def resolve_project_root(env: dict[str, str] | None = None) -> Path:
    """Resolve the canonical checkout without relying on the current directory."""

    source = env if env is not None else os.environ
    configured = str(source.get(_ROOT_ENV) or "").strip()
    return Path(configured).expanduser().resolve() if configured else _PACKAGE_ROOT


PROJECT_ROOT = resolve_project_root()


def project_path(*parts: str) -> Path:
    """Return a path below the configured canonical checkout."""

    return PROJECT_ROOT.joinpath(*parts)
