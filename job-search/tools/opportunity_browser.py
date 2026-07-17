"""Compatibility alias for browser opportunity normalization."""

from __future__ import annotations

import sys

from career_job_search.opportunities import browser as _implementation

sys.modules[__name__] = _implementation
