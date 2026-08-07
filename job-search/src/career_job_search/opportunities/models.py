"""Typed local models for broader job opportunities.

These models intentionally describe assistive, human-reviewed job leads. They
do not include any auto-apply or live-submission capability.
"""

from __future__ import annotations

import re
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from career_job_search.core.time import utc_now_iso


class OpportunitySourceKind(StrEnum):
    MANUAL_INBOX = "manual_inbox"
    COMPANY_SITE = "company_site"
    ATS = "ats"
    JOB_BOARD = "job_board"
    JOB_ALERT = "job_alert"
    WEB_SEARCH = "web_search"
    RECRUITER = "recruiter"


class OpportunityStatus(StrEnum):
    NEW = "new"
    MATCHED = "matched"
    REVIEW = "review"
    APPLY_READY = "apply_ready"
    APPLIED = "applied"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    FOLLOW_UP = "follow_up"


OpportunityAction = Literal[
    "review",
    "tailor_cv",
    "make_pack",
    "apply_manual",
    "contact_recruiter",
    "skip",
    "follow_up",
    "wait",
]

OpportunityLiveStatus = Literal["live", "closed", "unverified", "unknown"]


def normalise_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw or raw.lower() == "n/a":
        return ""
    parsed = urlsplit(raw)
    if not parsed.scheme:
        parsed = urlsplit("https://" + raw.lstrip("/"))
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def company_title_location_key(company: str, title: str, location: str) -> str:
    parts = [slug_key(company), slug_key(title), slug_key(location)]
    return "ctl:" + "|".join(part for part in parts if part)


def native_source_identity(source: str, native_source_id: str) -> str:
    return f"native:{slug_key(source)}|{slug_key(native_source_id)}"


def opportunity_id_from_key(key: str) -> str:
    digest = sha256((key or "opportunity").encode("utf-8")).hexdigest()[:16]
    return f"opp_{digest}"


def content_hash_from_parts(*parts: str) -> str:
    normalized = "\n".join(" ".join((part or "").split()).lower() for part in parts)
    return sha256(normalized.encode("utf-8")).hexdigest()


class OpportunityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_facts: list[str] = Field(default_factory=list)
    company_facts: list[str] = Field(default_factory=list)
    role_facts: list[str] = Field(default_factory=list)
    location_facts: list[str] = Field(default_factory=list)
    cv_fit_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class OpportunityMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    best_variant: str = ""
    score: float = 0.0
    fit_score: float = 0.0
    cv_score: float = 0.0
    location_score: float = 0.0
    role_track_score: float = 0.0
    source_score: float = 0.0
    salary_score: float = 0.0
    deadline_score: float = 0.0
    risk_penalty: float = 0.0
    role_track: str = ""
    runner_up_variant: str = ""
    runner_up_score: float = 0.0
    margin_over_second: float = 0.0
    confidence: str = ""
    variant_scores: list[dict[str, Any]] = Field(default_factory=list)
    keyword_hits: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    explanation: dict[str, str] = Field(default_factory=dict)


class OpportunityPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str = ""
    pack_dir: str = ""
    files: dict[str, str] = Field(default_factory=dict)
    generated_at: str = ""


class Opportunity(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    opportunity_id: str = ""
    source: str
    source_url: str = ""
    source_kind: OpportunitySourceKind
    native_source_id: str = ""
    canonical_identity: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    location_eligibility: str = ""
    eligibility_reason: str = ""
    first_eligible_at: str = ""
    remote_policy: str = ""
    description: str = ""
    salary_text: str = ""
    deadline: str = ""
    discovered_at: str = Field(default_factory=utc_now_iso)
    first_seen_at: str = ""
    last_seen_at: str = ""
    last_checked_at: str = ""
    source_updated_at: str = ""
    live_status: OpportunityLiveStatus = "unknown"
    live_checked_at: str = ""
    live_check_method: str = ""
    live_check_note: str = ""
    content_hash: str = ""
    likely_closed: bool = False
    duplicate_cluster_id: str = ""
    status: OpportunityStatus = OpportunityStatus.NEW
    dedupe_key: str = ""
    evidence: OpportunityEvidence = Field(default_factory=OpportunityEvidence)
    match: OpportunityMatch | None = None
    next_action: OpportunityAction = "review"
    pack: OpportunityPack | None = None

    @model_validator(mode="after")
    def fill_identity(self) -> Opportunity:
        self.source_url = normalise_url(self.source_url)
        if not self.canonical_identity:
            if self.native_source_id:
                self.canonical_identity = native_source_identity(
                    self.source, self.native_source_id
                )
            else:
                self.canonical_identity = company_title_location_key(
                    self.company, self.title, self.location
                )
        if not self.dedupe_key:
            if self.native_source_id:
                self.dedupe_key = self.canonical_identity
            elif self.source_url:
                self.dedupe_key = f"url:{self.source_url}"
            else:
                self.dedupe_key = company_title_location_key(
                    self.company, self.title, self.location
                )
        if not self.opportunity_id:
            self.opportunity_id = opportunity_id_from_key(self.canonical_identity)
        if not self.first_seen_at:
            self.first_seen_at = self.discovered_at
        if not self.last_seen_at:
            self.last_seen_at = self.discovered_at
        if not self.last_checked_at:
            self.last_checked_at = self.discovered_at
        if not self.content_hash:
            self.content_hash = content_hash_from_parts(
                self.title,
                self.company,
                self.location,
                self.remote_policy,
                self.description,
                self.salary_text,
                self.deadline,
            )
        self.next_action = next_action_for_opportunity(self)
        return self

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def next_action_for_opportunity(opportunity: Opportunity) -> OpportunityAction:
    if opportunity.likely_closed:
        return "wait"
    if opportunity.live_status == "closed":
        return "wait"
    if opportunity.live_status == "unverified":
        return "review"
    if opportunity.status in {OpportunityStatus.SKIPPED, OpportunityStatus.EXPIRED}:
        return "wait"
    if opportunity.status == OpportunityStatus.APPLIED:
        return "follow_up"
    if opportunity.status == OpportunityStatus.FOLLOW_UP:
        return "follow_up"
    if opportunity.status == OpportunityStatus.APPLY_READY:
        return "make_pack"

    risk_flags = set(opportunity.evidence.risk_flags)
    if risk_flags.intersection(
        {
            "duplicate",
            "language_requirement_risk",
            "location_ineligible",
            "possible_scam",
            "role_family_mismatch",
            "visa_location_risk",
        }
    ):
        return "skip"
    if "third_party_recruiter_only" in risk_flags:
        return "contact_recruiter"
    if opportunity.match:
        if opportunity.match.score < 8 or "low_cv_score" in risk_flags:
            return "skip"
        if opportunity.match.margin_over_second < 5:
            return "tailor_cv"
        if opportunity.status == OpportunityStatus.MATCHED:
            return "review"
    return "review"
