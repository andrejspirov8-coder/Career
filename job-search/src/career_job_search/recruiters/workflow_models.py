"""Typed recruiter workflow domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator


class WorkflowStage(StrEnum):
    DISCOVER = "discover"
    VALIDATE = "validate"
    ENRICH = "enrich"
    RANK = "rank"
    PREPARE_DISPATCH = "prepare_dispatch"
    DISPATCH = "dispatch"
    FOLLOW_UP = "follow_up"
    REPORT = "report"


class WorkflowMode(StrEnum):
    DRY_RUN = "dry_run"
    LIVE = "live"


class CandidateProfile(BaseModel):
    profile_url: str = ""
    name: str = ""
    headline: str = ""
    company: str = ""
    location: str = ""
    variant_slug: str = ""
    persona: str = ""
    search_intent: str = ""
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_url")
    @classmethod
    def _canonicalise_url(cls, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return ""
        parsed = urlsplit(raw)
        if not parsed.scheme:
            parsed = urlsplit("https://" + raw.lstrip("/"))
        host = (parsed.netloc or "www.linkedin.com").lower()
        if host == "linkedin.com":
            host = "www.linkedin.com"
        path = parsed.path.rstrip("/")
        return urlunsplit(("https", host, path, "", ""))


class CompanyProfile(BaseModel):
    company: str = ""
    relevance_score: float = Field(default=0.0, ge=0.0, le=100.0)
    rationale: str = ""
    flags: list[str] = Field(default_factory=list)
    web_url: str = ""


class OutreachDraft(BaseModel):
    profile_url: str = ""
    note: str = ""
    evidence_cited: str = ""
    status: str = "draft"
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )


class WorkflowStep(BaseModel):
    stage: WorkflowStage
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    run_id: str
    mode: WorkflowMode = WorkflowMode.DRY_RUN
    started_at: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )
    finished_at: str | None = None
    dry_run: bool = True
    stages: list[WorkflowStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    profile_url: str = ""
    note_hash: str = ""
    approved: bool = False
    reason: str = ""


class WorkflowStateSnapshot(BaseModel):
    run: WorkflowRun
    current_stage: WorkflowStage
    blockers: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
