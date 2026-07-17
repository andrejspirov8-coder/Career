#!/usr/bin/env python3
"""Compatibility command for read-only LinkedIn opportunity discovery."""

from __future__ import annotations

import sys

from career_job_search.integrations.linkedin import opportunities as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
