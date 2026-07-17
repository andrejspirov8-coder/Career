"""Compatibility alias for recruiter matching and outreach helpers."""

from __future__ import annotations

import sys

from career_job_search.recruiters import matching as _implementation

sys.modules[__name__] = _implementation
