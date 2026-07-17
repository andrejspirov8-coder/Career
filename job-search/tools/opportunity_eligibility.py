"""Compatibility alias for opportunity eligibility rules."""

from __future__ import annotations

import sys

from career_job_search.opportunities import eligibility as _implementation

sys.modules[__name__] = _implementation
