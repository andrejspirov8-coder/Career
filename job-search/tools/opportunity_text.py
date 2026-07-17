"""Compatibility alias for opportunity text normalization."""

from __future__ import annotations

import sys

from career_job_search.opportunities import text as _implementation

sys.modules[__name__] = _implementation
