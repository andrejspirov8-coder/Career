#!/usr/bin/env python3
"""Compatibility command for the opportunity workflow."""

from __future__ import annotations

import sys

from career_job_search.opportunities import orchestrator as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
