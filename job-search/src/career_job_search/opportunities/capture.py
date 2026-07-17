"""Safe manual opportunity capture without fetching the supplied URL."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from career_job_search.cvs.matching import parse_job_file
from career_job_search.opportunities.matching import (
    DEFAULT_ROLE_TRACKS,
    match_opportunity,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
    normalise_url,
)
from career_job_search.opportunities.normalization import infer_remote_policy
from career_job_search.opportunities.preferences import (
    SearchPreferences,
    load_search_preferences,
)
from career_job_search.opportunities.repository import (
    DEFAULT_OPPORTUNITY_DB,
    get_opportunity,
    record_action,
    upsert_opportunities,
)


class OpportunityCaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(default="", max_length=2048)
    text: str = Field(default="", max_length=50_000)
    title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)

    @field_validator("url", "text", "title", "company", "location")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value:
            return ""
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Job URL must be a normal HTTP or HTTPS link.")
        return value

    @model_validator(mode="after")
    def require_url_or_text(self) -> OpportunityCaptureInput:
        if not self.url and not self.text:
            raise ValueError("Paste a job URL or some job text.")
        return self


def _host_label(url: str) -> str:
    if not url:
        return ""
    host = (urlsplit(url).hostname or "").lower()
    for prefix in ("www.", "jobs.", "careers."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _title_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    candidate = parts[-1] if parts else ""
    if candidate and not candidate.isdigit() and len(candidate) <= 100:
        title = re.sub(r"[-_]+", " ", candidate).strip()
        if len(title) >= 4:
            return title.title()
    host = _host_label(url)
    return f"Saved job from {host}" if host else "Saved job link"


def _plain_text_title(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if 3 <= len(first) <= 160:
        return first
    return "Pasted job description"


def _location_from_text(text: str) -> str:
    lowered = text.casefold()
    if "vilnius" in lowered:
        return "Vilnius"
    if "lithuania" in lowered or "lietuva" in lowered:
        return "Lithuania"
    if "remote eu" in lowered or "remote europe" in lowered:
        return "Remote EU"
    if "remote" in lowered:
        return "Remote"
    return ""


def _capture_parts(capture: OpportunityCaptureInput) -> dict[str, str]:
    looks_structured = bool(
        capture.text
        and re.search(r"(?mi)^(TITLE|COMPANY|URL|SOURCE):", capture.text)
        and re.search(r"(?m)^---\s*$", capture.text)
    )
    parsed = parse_job_file(capture.text) if looks_structured else {}
    description = str(parsed.get("body") if looks_structured else capture.text)
    title = capture.title or str(parsed.get("title") or "")
    company = capture.company or str(parsed.get("company") or "")
    url = capture.url or str(parsed.get("url") or "")
    if url:
        OpportunityCaptureInput(url=url, text=description or "captured link")
    if not title:
        title = _plain_text_title(description) if description else _title_from_url(url)
    location = capture.location or _location_from_text(
        " ".join((title, company, description))
    )
    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "description": description,
    }


def _scoring_config(preferences: SearchPreferences) -> dict[str, Any]:
    tracks = [dict(track) for track in DEFAULT_ROLE_TRACKS]
    if preferences.target_roles:
        tracks.append(
            {
                "name": "user_search_profile",
                "weight": 1.5,
                "keywords": list(preferences.target_roles),
            }
        )
    return {
        "priority_regions": list(preferences.priority_locations),
        "role_tracks": tracks,
    }


def capture_opportunity(
    payload: dict[str, Any],
    *,
    db_path=DEFAULT_OPPORTUNITY_DB,
    search_preferences: SearchPreferences | None = None,
) -> dict[str, Any]:
    capture = OpportunityCaptureInput.model_validate(payload)
    parts = _capture_parts(capture)
    normalized_url = normalise_url(parts["url"])
    identity_material = normalized_url or "\n".join(
        (parts["title"], parts["company"], parts["location"], parts["description"])
    )
    identity = f"capture:{sha256(identity_material.encode('utf-8')).hexdigest()[:24]}"
    host = _host_label(parts["url"])
    opportunity = Opportunity(
        source=f"dashboard_capture:{host}" if host else "dashboard_capture",
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        source_url=parts["url"],
        canonical_identity=identity,
        title=parts["title"],
        company=parts["company"],
        location=parts["location"],
        remote_policy=infer_remote_policy(
            " ".join((parts["title"], parts["location"], parts["description"]))
        ),
        description=parts["description"],
        live_status="unverified",
        live_check_method="dashboard_capture",
        live_check_note="captured_without_fetch",
        evidence=OpportunityEvidence(
            source_facts=["dashboard:manual_capture", f"host:{host}" if host else ""],
            company_facts=[parts["company"]] if parts["company"] else [],
            role_facts=[parts["title"]] if parts["title"] else [],
            location_facts=[parts["location"]] if parts["location"] else [],
            confidence=0.45,
        ),
    )
    opportunity.evidence.source_facts = [
        fact for fact in opportunity.evidence.source_facts if fact
    ]
    preferences = search_preferences or load_search_preferences()
    match_opportunity(opportunity, scoring_config=_scoring_config(preferences))
    for flag in ("needs_live_verification", "link_review_required"):
        if flag not in opportunity.evidence.risk_flags:
            opportunity.evidence.risk_flags.append(flag)
    opportunity.live_status = "unverified"
    upsert_opportunities([opportunity], db_path=db_path)
    stored = get_opportunity(opportunity.opportunity_id, db_path=db_path)
    if stored is None:
        raise RuntimeError("Captured opportunity could not be saved.")
    record_action(
        opportunity=stored,
        action_type="capture_manual",
        old_status=stored.status,
        operator_source="dashboard",
        metadata={
            "capture_kind": "url_and_text"
            if parts["url"] and parts["description"]
            else "url"
            if parts["url"]
            else "text",
            "text_length": len(parts["description"]),
        },
        db_path=db_path,
    )
    return {
        "ok": True,
        "opportunity_id": stored.opportunity_id,
        "title": stored.title,
        "company": stored.company,
        "status": stored.status.value,
        "live_status": stored.live_status,
        "fetched_url": False,
    }
