from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException, status

from career_job_search.api.context import current_user_id

TOKEN_ENV_KEY = "CAREER_DASHBOARD_TOKEN"  # noqa: S105  # env var key name, not a secret
LEGACY_TOKEN = "local-dev"  # noqa: S105  # fallback for local dev only


def _get_expected_token() -> str:
    return os.environ.get(TOKEN_ENV_KEY, "")


def _is_supabase_jwt(token: str) -> bool:
    parts = token.split(".")
    return len(parts) == 3 and parts[0].startswith("eyJ")


def _verify_supabase_jwt(token: str) -> str | None:
    try:
        from supabase import create_client

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            return None
        client = create_client(url, key)
        user = client.auth.get_user(token)
        if user is None:
            return None
        return user.user.id
    except Exception:
        return None


async def verify_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    if _is_supabase_jwt(token):
        supabase_uid = _verify_supabase_jwt(token)
        if supabase_uid is not None:
            current_user_id.set(supabase_uid)
            return supabase_uid

    expected = _get_expected_token()
    if not expected:
        expected = LEGACY_TOKEN
    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )
    current_user_id.set("local-user")
    return "local-user"
