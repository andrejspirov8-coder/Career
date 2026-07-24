#!/usr/bin/env python3
"""Compatibility command for the notification inbox."""

from __future__ import annotations

import json
import sys

from career_job_search.core.schema import NOTIFICATIONS_OVERVIEW_SCHEMA
from career_job_search.notifications import center as _implementation

if __name__ == "__main__":
    if "--schema" in sys.argv:
        print(json.dumps(NOTIFICATIONS_OVERVIEW_SCHEMA, indent=2))
        sys.exit(0)
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation