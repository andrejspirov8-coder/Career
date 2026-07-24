#!/usr/bin/env python3
"""Compatibility command for local CV and application drafting."""

from __future__ import annotations

import json
import sys

from career_job_search.core.schema import LOCAL_DRAFTING_SCHEMA
from career_job_search.cvs import drafting as _implementation

if __name__ == "__main__":
    if "--schema" in sys.argv:
        print(json.dumps(LOCAL_DRAFTING_SCHEMA, indent=2))
        sys.exit(0)
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation