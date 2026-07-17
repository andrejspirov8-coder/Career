"""Compatibility alias for LinkedIn selectors and page safety checks."""

from __future__ import annotations

import sys

from career_job_search.integrations.linkedin import selectors as _implementation

sys.modules[__name__] = _implementation
