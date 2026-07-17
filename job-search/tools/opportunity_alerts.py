"""Compatibility alias for opportunity alert normalization."""

from __future__ import annotations

import sys

from career_job_search.opportunities import alerts as _implementation

sys.modules[__name__] = _implementation
