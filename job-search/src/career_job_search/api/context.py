from __future__ import annotations

import contextvars

current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_id", default="local-user"
)
