from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from career_job_search.api.auth import verify_token
from career_job_search.api.routers.agent import router as agent_router
from career_job_search.api.routers.auth import router as auth_router
from career_job_search.api.routers.checklist import router as checklist_router
from career_job_search.api.routers.helpers import router as helpers_router
from career_job_search.api.routers.linkedin import router as linkedin_router
from career_job_search.api.routers.preferences import router as preferences_router
from career_job_search.api.routers.profiles import router as profiles_router
from career_job_search.api.routers.settings_runtime import (
    router as settings_runtime_router,
)
from career_job_search.api.routers.sources import router as sources_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Career API",
        description="Backend API for job-search automation, CV management, recruiter scoring, and opportunity pipeline.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.include_router(helpers_router)
    app.include_router(sources_router)
    app.include_router(linkedin_router)
    app.include_router(profiles_router)
    app.include_router(settings_runtime_router)
    app.include_router(preferences_router)
    app.include_router(checklist_router)
    app.include_router(auth_router)
    app.include_router(agent_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/me")
    async def me(user: str = Depends(verify_token)):
        return {"user": user}

    return app
