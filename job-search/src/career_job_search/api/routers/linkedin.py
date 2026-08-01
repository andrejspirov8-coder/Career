from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from career_job_search.api.auth import verify_token
from career_job_search.integrations.linkedin.config_helper import (
    read_config,
    write_config,
)

router = APIRouter(prefix="/api/v1/settings/linkedin", dependencies=[Depends(verify_token)])


@router.get("/")
async def get_linkedin_config() -> dict[str, Any]:
    return read_config()


@router.post("/")
async def save_linkedin_config(data: dict[str, Any]) -> dict[str, Any]:
    write_config(data)
    return read_config()
