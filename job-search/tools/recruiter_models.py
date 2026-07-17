"""Compatibility alias for recruiter workflow models."""

from __future__ import annotations

import sys

from career_job_search.recruiters import workflow_models as _implementation

sys.modules[__name__] = _implementation
