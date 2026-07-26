"""Shared hiring-network domain records with no workflow dependencies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from career_job_search.core.linkedin_urls import canonical_linkedin_profile_url

Persona = Literal[
    "recruiter_hr",
    "executive_search",
    "hiring_manager",
    "retail_area_leader",
    "store_director",
    "operations_leader",
    "it_business_leader",
    "low_relevance",
]
SendTier = Literal["auto_send", "queue_review", "skip"]
Decision = Literal["approved", "review", "skip"]
ScreenState = Literal[
    "profile_loaded",
    "connect_visible",
    "pending_visible",
    "login_wall",
    "checkpoint",
    "captcha",
    "unusual_activity",
    "unknown",
]


class ProfileCandidate(BaseModel):
    """Profile facts scraped from LinkedIn or loaded from a scout action plan."""

    model_config = ConfigDict(extra="forbid")

    profile_url: str
    name: str = ""
    headline: str = ""
    company: str = ""
    location: str = ""
    scraped_text: str = ""
    search_variant_slug: str = ""
    source_backend: str = ""
    target_company: str = ""
    target_opportunity_id: str = ""
    target_role_title: str = ""
    target_company_verified: bool = False

    @field_validator("profile_url")
    @classmethod
    def validate_linkedin_profile_url(cls, value: str) -> str:
        canonical = canonical_linkedin_profile_url(value)
        if not canonical:
            raise ValueError("profile_url must be a LinkedIn /in/ profile URL")
        return canonical

    def text_blob(self) -> str:
        return "\n".join(
            item
            for item in (
                self.name,
                self.headline,
                self.company,
                self.location,
                self.scraped_text,
            )
            if item.strip()
        )


class PersonaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona: Persona
    hiring_authority_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    risk_flags: list[str] = Field(default_factory=list, max_length=8)


class CvMatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    best_cv_variant: str
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    runner_up_variant: str = ""
    margin_over_second: float = 0.0


class HistorySignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sent_count: int = 0
    accepted_count: int = 0
    reply_count: int = 0
    interview_count: int = 0

    def score(self) -> float:
        if self.sent_count <= 0:
            return 50.0
        accept = self.accepted_count / self.sent_count
        reply = self.reply_count / self.sent_count
        interview = self.interview_count / self.sent_count
        return max(
            0.0,
            min(100.0, 100.0 * (0.4 * accept + 0.4 * reply + 0.2 * interview)),
        )


class RankedInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: ProfileCandidate
    persona: PersonaDecision
    cv_match: CvMatchDecision
    rank_score: float = Field(ge=0, le=100)
    send_tier: SendTier
    note: str
    risk_flags: list[str] = Field(default_factory=list, max_length=12)
    decision: Decision
    note_reason: str = ""

    @field_validator("note")
    @classmethod
    def validate_note_length(cls, value: str) -> str:
        if len(value) > 280:
            raise ValueError("note must be 280 characters or fewer")
        return value

    @model_validator(mode="after")
    def validate_decision_tier_consistency(self) -> Self:
        if self.decision == "approved" and self.send_tier != "auto_send":
            raise ValueError("approved invites must use send_tier=auto_send")
        if self.decision == "skip" and self.send_tier != "skip":
            raise ValueError("skipped invites must use send_tier=skip")
        return self

    def to_action_record(self) -> dict[str, Any]:
        return {
            "schema": "hiring_network_invite_v1",
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "profile_url": self.candidate.profile_url,
            "name": self.candidate.name,
            "headline": self.candidate.headline,
            "company": self.candidate.company,
            "location": self.candidate.location,
            "persona": self.persona.persona,
            "persona_confidence": round(self.persona.confidence, 4),
            "hiring_authority_score": round(self.persona.hiring_authority_score, 4),
            "cv_variant": self.cv_match.best_cv_variant,
            "cv_score": round(self.cv_match.score, 4),
            "cv_confidence": round(self.cv_match.confidence, 4),
            "rank_score": round(self.rank_score, 4),
            "send_tier": self.send_tier,
            "decision": self.decision,
            "risk_flags": self.risk_flags,
            "persona_evidence": self.persona.evidence,
            "cv_evidence": self.cv_match.evidence,
            "note": self.note,
            "note_reason": self.note_reason,
            "source_backend": self.candidate.source_backend,
            "target_company": self.candidate.target_company,
            "target_opportunity_id": self.candidate.target_opportunity_id,
            "target_role_title": self.candidate.target_role_title,
            "target_company_verified": self.candidate.target_company_verified,
        }


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: str = Field("hiring_network_run_state_v1", alias="schema")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )
    queue: list[RankedInvite] = Field(default_factory=list)
    sent_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    audit_records: list[dict[str, Any]] = Field(default_factory=list)
