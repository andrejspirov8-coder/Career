#!/usr/bin/env python3
"""Compatibility adapter for recruiter run-state persistence."""

from __future__ import annotations

import sys

from career_job_search.recruiters import run_state as _implementation

sys.modules[__name__] = _implementation
