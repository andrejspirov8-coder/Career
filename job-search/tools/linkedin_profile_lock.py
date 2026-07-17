#!/usr/bin/env python3
"""Compatibility adapter for LinkedIn browser-profile locks."""

from __future__ import annotations

import sys

from career_job_search.integrations.linkedin import profile_lock as _implementation

sys.modules[__name__] = _implementation
