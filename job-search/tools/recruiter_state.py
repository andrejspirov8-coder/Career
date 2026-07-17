"""Compatibility alias for recruiter persistence and approvals."""

from __future__ import annotations

import sys

from career_job_search.recruiters import repository as _implementation

sys.modules[__name__] = _implementation
