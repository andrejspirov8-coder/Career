#!/usr/bin/env python3
"""Compatibility adapter for recruiter agent tools."""

from __future__ import annotations

import sys

from career_job_search.recruiters import agent_tools as _implementation

sys.modules[__name__] = _implementation
