#!/usr/bin/env python3
"""Compatibility command for matching one job to CV variants."""

from __future__ import annotations

import sys

from career_job_search.opportunities import job_match as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
