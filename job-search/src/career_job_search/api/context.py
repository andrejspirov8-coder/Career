"""Identity context for API-facing helpers.

Re-exports `current_user_id` from `career_job_search.core.context` so both
API routers and domain repositories share the same contextvar instance.
"""

from __future__ import annotations

from career_job_search.core.context import current_user_id

__all__ = ["current_user_id"]
