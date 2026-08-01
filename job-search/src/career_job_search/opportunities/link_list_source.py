"""Configured human-review links for opportunity discovery."""

from __future__ import annotations

from typing import Any

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)


def discover_link_list(
    config: dict[str, Any],
    name: str,
    kind: OpportunitySourceKind,
) -> list[Opportunity]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    if not isinstance(block, dict) or not bool(block.get("enabled", False)):
        return []

    rows: list[Opportunity] = []
    for item in block.get("links") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Manual review link")
        company = str(item.get("company") or "")
        url = str(item.get("url") or "")
        rows.append(
            Opportunity(
                source=name,
                source_kind=kind,
                source_url=url,
                title=title,
                company=company,
                location=str(item.get("location") or ""),
                description=str(item.get("description") or title),
                evidence=OpportunityEvidence(
                    source_facts=[url] if url else [],
                    role_facts=[title],
                    risk_flags=["link_review_required"],
                    confidence=0.4,
                ),
            )
        )
    return rows
