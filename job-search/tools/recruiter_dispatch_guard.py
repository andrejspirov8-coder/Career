"""Compatibility alias for recruiter dispatch guards."""

from __future__ import annotations

import sys

from career_job_search.recruiters import dispatch_guard as _implementation

sys.modules[__name__] = _implementation
