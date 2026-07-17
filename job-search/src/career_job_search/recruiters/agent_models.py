"""Structured agent records independent of any Ollama implementation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DiscoveryExtraction(BaseModel):
    name: str = ""
    headline: str = ""
    company: str = ""
    profile_url: str = ""
    location: str = "Lithuania"
    discovery_notes: str = ""
    relevance_0_100: float = Field(default=0, ge=0, le=100)


class DiscoveryBatchResult(BaseModel):
    candidates: list[DiscoveryExtraction] = Field(default_factory=list)


class CompanyAnalysis(BaseModel):
    relevance_0_100: float = Field(default=0, ge=0, le=100)
    flags: list[str] = Field(default_factory=list)
    rationale: str = ""
    recommended_status: Literal["approved", "review", "reject"] = "review"


class OutreachNote(BaseModel):
    note: str = ""
    evidence_cited: str = ""

    @field_validator("note")
    @classmethod
    def cap_note(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) > 280:
            return value[:277].rstrip(" ,.;:") + "..."
        return value


class SupervisorDecision(BaseModel):
    action: Literal["approved", "review", "reject"] = "review"
    reason: str = ""
