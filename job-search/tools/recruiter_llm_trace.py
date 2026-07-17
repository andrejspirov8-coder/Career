#!/usr/bin/env python3
"""Compatibility adapter for recruiter model tracing."""

from __future__ import annotations

import sys

from career_job_search.recruiters import llm_trace as _implementation

sys.modules[__name__] = _implementation
