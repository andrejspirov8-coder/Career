#!/usr/bin/env python3
"""Compatibility command for recruiter dashboard review."""

from __future__ import annotations

import json
import sys

from career_job_search.core.schema import RECRUITER_OVERVIEW_SCHEMA
from career_job_search.recruiters import dashboard_adapter as _implementation

if __name__ == "__main__":
    if "--schema" in sys.argv:
        print(json.dumps(RECRUITER_OVERVIEW_SCHEMA, indent=2))
        sys.exit(0)
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation