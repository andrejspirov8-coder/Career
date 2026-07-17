"""Compatibility alias for opportunity domain models."""

from __future__ import annotations

import sys

from career_job_search.opportunities import models as _implementation

sys.modules[__name__] = _implementation
