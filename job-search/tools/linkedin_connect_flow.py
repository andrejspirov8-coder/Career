#!/usr/bin/env python3
"""Compatibility adapter for the LinkedIn connection flow."""

from __future__ import annotations

import sys

from career_job_search.integrations.linkedin import connect_flow as _implementation

sys.modules[__name__] = _implementation
