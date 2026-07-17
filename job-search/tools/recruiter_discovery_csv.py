#!/usr/bin/env python3
"""Compatibility adapter for recruiter discovery CSV helpers."""

from __future__ import annotations

import sys

from career_job_search.recruiters import discovery_csv as _implementation

sys.modules[__name__] = _implementation
