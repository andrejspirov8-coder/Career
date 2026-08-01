from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from career_job_search.api.auth import verify_token
from career_job_search.recruiters.config import Settings, load_settings, save_settings

router = APIRouter(prefix="/api/v1/settings/runtime", dependencies=[Depends(verify_token)])


@router.get("/")
async def get_runtime_settings() -> dict[str, Any]:
    settings = load_settings()
    return settings.model_dump(mode="json")


@router.post("/")
async def save_runtime_settings(data: dict[str, Any]) -> dict[str, Any]:
    settings = Settings.model_validate(data)
    save_settings(settings)
    return settings.model_dump(mode="json")
