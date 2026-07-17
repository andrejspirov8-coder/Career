"""Compatibility alias for opportunity source adapters."""

from __future__ import annotations

import sys

from career_job_search.opportunities import sources as _implementation

sys.modules[__name__] = _implementation
