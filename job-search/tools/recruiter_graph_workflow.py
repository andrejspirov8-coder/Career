"""Compatibility alias for the resumable recruiter supervisor."""

from __future__ import annotations

import sys

from career_job_search.recruiters import graph_workflow as _implementation

sys.modules[__name__] = _implementation
