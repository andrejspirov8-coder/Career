"""ATS provider payload normalization helpers."""

from __future__ import annotations

from typing import Any

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)
from career_job_search.opportunities.normalization import infer_remote_policy


def normalize_ats_posting(
    provider: str,
    payload: dict[str, Any],
    *,
    company: str = "",
    source_url: str = "",
    source_name: str = "",
) -> Opportunity:
    name = provider.strip().lower()
    title = ""
    location = ""
    url = source_url
    description = ""
    ats_id = ""

    if name == "greenhouse":
        title = str(payload.get("title") or "")
        loc = payload.get("location") or {}
        location = str(loc.get("name") if isinstance(loc, dict) else loc or "")
        url = str(payload.get("absolute_url") or url)
        description = str(payload.get("content") or "")
        ats_id = str(payload.get("id") or "")
    elif name == "lever":
        title = str(payload.get("text") or payload.get("title") or "")
        categories = payload.get("categories") or {}
        location = str(
            categories.get("location") if isinstance(categories, dict) else ""
        )
        url = str(payload.get("hostedUrl") or payload.get("applyUrl") or url)
        description = str(
            payload.get("descriptionPlain") or payload.get("description") or ""
        )
        ats_id = str(payload.get("id") or "")
    elif name == "ashby":
        title = str(payload.get("title") or "")
        loc = payload.get("location") or ""
        if isinstance(loc, dict):
            location = str(
                loc.get("name") or loc.get("location") or loc.get("city") or ""
            )
        else:
            location = str(loc)
        url = str(payload.get("jobUrl") or payload.get("applyUrl") or url)
        description = str(
            payload.get("descriptionPlain") or payload.get("description") or ""
        )
        ats_id = str(payload.get("id") or payload.get("jobId") or "")
    elif name == "smartrecruiters":
        title = str(payload.get("name") or payload.get("title") or "")
        loc = payload.get("location") or {}
        if isinstance(loc, dict):
            location = str(
                loc.get("city") or loc.get("name") or loc.get("country") or ""
            )
        else:
            location = str(loc or "")
        ref = payload.get("ref") or {}
        url = str(
            payload.get("url")
            or payload.get("applyUrl")
            or (ref.get("jobAd") if isinstance(ref, dict) else "")
            or url
        )
        description = str(payload.get("jobAd") or payload.get("description") or "")
        ats_id = str(payload.get("id") or "")
    else:
        raise ValueError(f"Unsupported ATS provider: {provider}")

    evidence = OpportunityEvidence(
        source_facts=[f"ats:{name}", f"ats_id:{ats_id}" if ats_id else ""],
        company_facts=[company] if company else [],
        role_facts=[title] if title else [],
        location_facts=[location] if location else [],
        confidence=0.7,
    )
    evidence.source_facts = [item for item in evidence.source_facts if item]
    return Opportunity(
        source=source_name or name,
        source_kind=OpportunitySourceKind.ATS,
        native_source_id=ats_id,
        source_url=url,
        title=title,
        company=company,
        location=location,
        remote_policy=infer_remote_policy(f"{title} {location} {description}"),
        description=description,
        evidence=evidence,
    )


def _provider_slug(config: dict[str, Any], *names: str) -> str:
    for name in names:
        value = str(config.get(name) or "").strip()
        if value:
            return value
    return ""


def _provider_source_name(provider: str, slug: str) -> str:
    return f"{provider}:{slug}" if slug else provider


def _payload_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []
