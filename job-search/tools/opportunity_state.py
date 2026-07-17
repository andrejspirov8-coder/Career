"""Compatibility alias for opportunity persistence."""

from __future__ import annotations

import sys

from career_job_search.opportunities import repository as _implementation

sys.modules[__name__] = _implementation
