#!/usr/bin/env python3
"""Compatibility command for the local recruiter model client."""

from __future__ import annotations

import sys

from career_job_search.recruiters import ollama_client as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation._main())
else:
    sys.modules[__name__] = _implementation
