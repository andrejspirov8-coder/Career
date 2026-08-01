from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from career_job_search.api.auth import verify_token
from career_job_search.cvs.profiles_helper import read_profiles, write_profiles

router = APIRouter(prefix="/api/v1/settings/cv-profiles", dependencies=[Depends(verify_token)])


@router.get("/")
async def get_profiles() -> dict[str, Any]:
    return read_profiles()


@router.post("/")
async def save_profiles(data: dict[str, Any]) -> dict[str, Any]:
    write_profiles(data)
    return read_profiles()
