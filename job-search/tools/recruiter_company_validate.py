#!/usr/bin/env python3
"""Compatibility command for recruiter-company validation."""

from __future__ import annotations

import sys

from career_job_search.recruiters import company_validation as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
