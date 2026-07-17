#!/usr/bin/env python3
"""Compatibility adapter for local recruiter agents."""

from __future__ import annotations

import sys

from career_job_search.recruiters import ollama_agents as _implementation

sys.modules[__name__] = _implementation
