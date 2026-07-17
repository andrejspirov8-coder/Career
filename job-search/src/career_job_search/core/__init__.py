"""Shared infrastructure primitives with no domain dependencies."""

from .limits import MAX_LIVE_DISPATCH
from .paths import PROJECT_ROOT, project_path

__all__ = ["MAX_LIVE_DISPATCH", "PROJECT_ROOT", "project_path"]
