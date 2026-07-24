#!/usr/bin/env python3
"""Compatibility command for private workspace controls."""

from __future__ import annotations

import json
import sys

from career_job_search.core.schema import WORKSPACE_CONTROLS_SCHEMA
from career_job_search.workspace import control as _implementation

if __name__ == "__main__":
    if "--schema" in sys.argv:
        print(json.dumps(WORKSPACE_CONTROLS_SCHEMA, indent=2))
        sys.exit(0)
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation