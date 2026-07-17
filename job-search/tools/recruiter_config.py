"""Compatibility alias for validated recruiter configuration."""

from __future__ import annotations

import sys

from career_job_search.recruiters import config as _implementation

sys.modules[__name__] = _implementation
