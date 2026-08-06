from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException, status

from career_job_search.api.context import current_user_id

TOKEN_ENV_KEY = "CAREER_DASHBOARD_TOKEN"  # noqa: S105  # environment variable name


def _get_expected_token() -> str:
    return os.environ.get(TOKEN_ENV_KEY, "").strip()


async def verify_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    expected = _get_expected_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{TOKEN_ENV_KEY} is not configured.",
        )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    scheme, separator, token = authorization.partition(" ")
    token = token.strip()
    if scheme.casefold() != "bearer" or not separator or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )

    current_user_id.set("local-user")
    return "local-user"
