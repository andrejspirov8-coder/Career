"""Compatibility alias for CV and job matching helpers."""

from __future__ import annotations

import sys

from career_job_search.cvs import matching as _implementation

sys.modules[__name__] = _implementation
