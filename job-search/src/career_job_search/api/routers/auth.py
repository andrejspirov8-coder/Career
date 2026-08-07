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


@router.post("/signup")
async def signup(body: SignupRequest, _user_id: str = Depends(verify_token)) -> dict:
    if os.environ.get("CAREER_ALLOW_LOCAL_SIGNUP", "").strip().casefold() != "true":
        raise HTTPException(status_code=403, detail="Local signup is disabled.")
    if not body.email or "@" not in body.email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(body.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )
    try:
        user = create_user(body.email, body.password)
        return {"ok": True, "user_id": user.user_id, "email": user.email}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/login")
async def login(body: LoginRequest) -> LoginResponse:
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
