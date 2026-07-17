"""Compatibility alias for opportunity liveness checks."""

from __future__ import annotations

import sys

from career_job_search.opportunities import live as _implementation

sys.modules[__name__] = _implementation
