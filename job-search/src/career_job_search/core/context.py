"""Per-request identity propagation shared by domain repositories.

Domain repository functions read `current_user_id` to scope reads and writes
to the authenticated user. The default `local-user` keeps single-user CLI
workflows working without any authentication context.
"""

from __future__ import annotations

import contextvars

current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_id", default="local-user"
)
