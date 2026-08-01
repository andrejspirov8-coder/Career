from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from career_job_search.api.auth import verify_token
from career_job_search.api.user_store import create_user, get_user, verify_user

router = APIRouter(prefix="/api/v1/auth")


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user_id: str
    email: str
    supabase_access_token: str | None = None


def _supabase_sign_in(email: str, password: str) -> dict | None:
    """Authenticate against Supabase Auth. Returns session dict or None."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client

        client = create_client(url, key)
        session = client.auth.sign_in_with_password({"email": email, "password": password})
        if session and session.user and session.session:
            return {
                "user_id": session.user.id,
                "email": session.user.email or email,
                "access_token": session.session.access_token,
            }
    except Exception:
        return None
    return None


@router.post("/signup")
async def signup(body: SignupRequest) -> dict:
    if not body.email or "@" not in body.email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    try:
        user = create_user(body.email, body.password)
        return {"ok": True, "user_id": user.user_id, "email": user.email}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/login")
async def login(body: LoginRequest) -> LoginResponse:
    # 1. Try Supabase Auth first if configured
    supabase_result = _supabase_sign_in(body.email, body.password)
    if supabase_result is not None:
        return LoginResponse(
            ok=True,
            user_id=supabase_result["user_id"],
            email=supabase_result["email"],
            supabase_access_token=supabase_result["access_token"],
        )

    # 2. Fall back to local SQLite user store
    user = verify_user(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return LoginResponse(ok=True, user_id=user.user_id, email=user.email)


@router.get("/me")
async def me(user_id: str = Depends(verify_token)) -> dict:
    user = get_user(user_id)
    if user is None:
        return {"user_id": user_id, "email": None}
    return {"user_id": user.user_id, "email": user.email}
