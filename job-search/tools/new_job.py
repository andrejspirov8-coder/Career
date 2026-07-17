#!/usr/bin/env python3
"""Compatibility command for creating an inbox job file."""

from __future__ import annotations

import sys

from career_job_search.opportunities import new_job as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
