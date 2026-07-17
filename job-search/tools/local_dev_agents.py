#!/usr/bin/env python3
"""Compatibility command for local development-agent coordination."""

from __future__ import annotations

import sys

from career_job_search.dev_agents import coordinator as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
