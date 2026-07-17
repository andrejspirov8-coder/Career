"""Compatibility alias for recruiter web research."""

from __future__ import annotations

import sys

from career_job_search.recruiters import web_research as _implementation

sys.modules[__name__] = _implementation
