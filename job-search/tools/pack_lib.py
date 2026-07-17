"""Compatibility alias for application-pack helpers."""

from __future__ import annotations

import sys

from career_job_search.opportunities import packs as _implementation

sys.modules[__name__] = _implementation
