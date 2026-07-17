#!/usr/bin/env python3
"""Compatibility command for recruiter approval records."""

from __future__ import annotations

import sys

from career_job_search.recruiters import approval as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main(sys.argv[1:]))
else:
    sys.modules[__name__] = _implementation
