"""Compatibility alias for safe opportunity capture."""

from __future__ import annotations

import sys

from career_job_search.opportunities import capture as _implementation

sys.modules[__name__] = _implementation
