#!/usr/bin/env python3
"""Compatibility adapter for local development-agent models."""

from __future__ import annotations

import sys

from career_job_search.dev_agents import models as _implementation

sys.modules[__name__] = _implementation
