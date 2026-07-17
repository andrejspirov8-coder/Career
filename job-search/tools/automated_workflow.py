"""Compatibility alias for the preserved legacy workflow prototype."""

from __future__ import annotations

import sys

from career_job_search.automation import legacy_workflow as _implementation

sys.modules[__name__] = _implementation
