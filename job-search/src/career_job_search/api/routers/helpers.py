from __future__ import annotations

import importlib
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from career_job_search.api.auth import verify_token

HELPER_REGISTRY: dict[str, str] = {
    "analytics": "career_job_search.automation.analytics",
    "cvCatalogue": "tools.cv_catalogue",
    "cvStudio": "career_job_search.cvs.studio",
    "cvProfiles": "career_job_search.cvs.profiles_helper",
    "linkedinConfig": "career_job_search.integrations.linkedin.config_helper",
    "localDrafting": "career_job_search.cvs.drafting",
    "notifications": "career_job_search.notifications.center",
    "opportunities": "tools.opportunity_dashboard",
    "opportunitySources": "career_job_search.opportunities.sources_helper",
    "recruiters": "career_job_search.recruiters.dashboard_adapter",
    "searchPreferences": "career_job_search.opportunities.preferences",
    "settingsControl": "career_job_search.recruiters.settings_helper",
    "setupChecklist": "career_job_search.setup.checklist",
    "workspace": "tools.workspace_control",
    "automation": "tools.automation_control",
}

router = APIRouter(prefix="/api/v1/helpers", dependencies=[Depends(verify_token)])


class HelperRequest(BaseModel):
    args: list[str] = []
    input: str | None = None


class HelperResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ok: bool
    data: Any = None
    error: str | None = None
    schema: str = "career_python_helper_v1"  # type: ignore[assignment]


@router.post("/{name}")
async def run_helper(name: str, body: HelperRequest) -> HelperResponse:
    module_path = HELPER_REGISTRY.get(name)
    if module_path is None:
        raise HTTPException(status_code=404, detail=f"Unknown helper: {name}")

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot import helper: {exc}") from exc

    module = sys.modules.get(module_path, module)

    if not hasattr(module, "main"):
        raise HTTPException(
            status_code=500, detail=f"Helper {name} has no main() function"
        )

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 1
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exit_code = module.main(body.args)
        stdout_text = stdout_buf.getvalue()
        stderr_text = stderr_buf.getvalue()
    except Exception as exc:
        stderr_text = str(exc)
        exit_code = 1
        stdout_text = ""

    if stdout_text.strip():
        try:
            payload = json.loads(stdout_text)
            if isinstance(payload, dict):
                return HelperResponse(
                    ok=payload.get("ok", exit_code == 0),
                    data=payload.get("data"),
                    error=payload.get("error")
                    or (stderr_text if exit_code != 0 else None),
                )
        except json.JSONDecodeError:
            pass

    if exit_code != 0:
        return HelperResponse(
            ok=False, error=stderr_text or stdout_text or "Unknown error"
        )

    return HelperResponse(
        ok=True, data=stdout_text.strip() if stdout_text.strip() else None
    )
