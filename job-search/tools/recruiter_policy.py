"""Compatibility alias for recruiter safety policy."""

from __future__ import annotations

import sys

from career_job_search.recruiters import policy as _implementation

sys.modules[__name__] = _implementation
