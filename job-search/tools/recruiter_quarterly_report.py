#!/usr/bin/env python3
"""Compatibility command for the recruiter quarterly report."""

from __future__ import annotations

import sys

from career_job_search.recruiters import quarterly_report as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
