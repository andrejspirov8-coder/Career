from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from career_job_search.api.auth import verify_token
from career_job_search.setup.checklist import check_setup

router = APIRouter(
    prefix="/api/v1/setup/checklist", dependencies=[Depends(verify_token)]
)


@router.get("/")
async def get_checklist() -> dict[str, Any]:
    return check_setup()
