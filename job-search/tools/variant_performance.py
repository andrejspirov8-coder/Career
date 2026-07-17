#!/usr/bin/env python3
"""Compatibility command for CV variant performance reporting."""

from __future__ import annotations

import sys

from career_job_search.cvs import performance as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
