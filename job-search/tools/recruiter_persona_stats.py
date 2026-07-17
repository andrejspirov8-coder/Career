#!/usr/bin/env python3
"""Compatibility adapter for recruiter persona statistics."""

from __future__ import annotations

import sys

from career_job_search.recruiters import persona_stats as _implementation

sys.modules[__name__] = _implementation
