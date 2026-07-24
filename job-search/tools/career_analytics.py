#!/usr/bin/env python3
"""Compatibility command for career outcome analytics."""

from __future__ import annotations

import json
import sys

from career_job_search.automation import analytics as _implementation
from career_job_search.core.schema import ANALYTICS_OVERVIEW_SCHEMA

if __name__ == "__main__":
    if "--schema" in sys.argv:
        print(json.dumps(ANALYTICS_OVERVIEW_SCHEMA, indent=2))
        sys.exit(0)
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation