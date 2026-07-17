#!/usr/bin/env python3
"""Compatibility command for local CV and application drafting."""

from __future__ import annotations

import sys

from career_job_search.cvs import drafting as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
