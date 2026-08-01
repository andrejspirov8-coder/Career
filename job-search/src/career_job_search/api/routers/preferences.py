from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from career_job_search.api.auth import verify_token
from career_job_search.opportunities.preferences import (
    load_search_preferences,
    save_search_preferences,
)

router = APIRouter(prefix="/api/v1/settings/preferences", dependencies=[Depends(verify_token)])


@router.get("/")
async def get_preferences() -> dict[str, Any]:
    prefs = load_search_preferences()
    return prefs.model_dump(mode="json", by_alias=True)


@router.post("/")
async def save_preferences(data: dict[str, Any]) -> dict[str, Any]:
    prefs = save_search_preferences(data)
    return prefs.model_dump(mode="json", by_alias=True)
