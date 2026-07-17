#!/usr/bin/env python3
"""Compatibility adapter for recruiter agent context."""

from __future__ import annotations

import sys

from career_job_search.recruiters import agent_context as _implementation

sys.modules[__name__] = _implementation
