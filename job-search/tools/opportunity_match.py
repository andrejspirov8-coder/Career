"""Compatibility alias for opportunity matching."""

from __future__ import annotations

import sys

from career_job_search.opportunities import matching as _implementation

sys.modules[__name__] = _implementation
