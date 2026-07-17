"""Compatibility alias for local LinkedIn integration paths."""

from __future__ import annotations

import sys

from career_job_search.integrations.linkedin import paths as _implementation

sys.modules[__name__] = _implementation
