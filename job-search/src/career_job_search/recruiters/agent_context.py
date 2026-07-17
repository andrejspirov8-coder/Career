"""Pre-fetched context blobs for Ollama recruiter agents."""

from __future__ import annotations

import csv
from typing import Any

from career_job_search.cvs.context import cv_context_blob
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import (
    MCP_DISCOVERY_BATCH_JSONL,
    RECRUITERS_CSV,
)
from career_job_search.recruiters.history import company_history
from career_job_search.recruiters.persona_stats import load_persona_stats
from career_job_search.recruiters.web_models import WebSearchHit

HARD_REJECT_FLAGS = frozenset(
    {"outreach_exclude_term", "wrong_sector", "staffing_only"}
)


def _already_contacted(profile_url: str) -> bool:
    canon = lis.canonical_profile_url(profile_url)
    if not canon or not RECRUITERS_CSV.is_file():
        return False
    with RECRUITERS_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if lis.canonical_profile_url(row.get("profile_url") or "") == canon:
                status = (row.get("status") or "").strip().lower()
                if status in {"sent", "pending", "accepted"}:
                    return True
    return False


def _mcp_batch_match(profile_url: str) -> bool:
    if not MCP_DISCOVERY_BATCH_JSONL.is_file():
        return False
    canon = lis.canonical_profile_url(profile_url)
    for line in MCP_DISCOVERY_BATCH_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        import json

        stub = json.loads(line)
        if lis.canonical_profile_url(stub.get("profile_url") or "") == canon:
            return True
    return False


def discovery_context(
    hit: WebSearchHit, *, variant_slug: str, full_cfg: dict[str, Any]
) -> dict[str, Any]:
    url = lis.canonical_profile_url(hit.url) or hit.url
    return {
        "variant_focus": variant_slug,
        "hit_source": hit.source,
        "already_contacted": _already_contacted(url) if url else False,
        "mcp_batch_match": _mcp_batch_match(url) if url else False,
    }


_company_history = company_history


def company_context(
    *,
    company: str,
    headline: str,
    web_blob: str,
    full_cfg: dict[str, Any],
) -> dict[str, Any]:
    hn = full_cfg.get("hiring_network") or {}
    terms = [str(x) for x in hn.get("track_aligned_company_terms") or []]
    blob_l = f"{company} {headline} {web_blob}".lower()
    matched = [t for t in terms if t.lower() in blob_l][:8]
    history = _company_history(company)
    return {
        "web_blob_preview": web_blob[:1200],
        "rubric_terms_matched": matched,
        "prior_outcomes_count": history["sent"],
        "company_history": history,
    }


def outreach_context(
    *,
    name: str,
    headline: str,
    company: str,
    persona: str,
    cv_variant: str,
    evidence: list[str] | None = None,
    full_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats = load_persona_stats()
    entry = stats.get(persona) or {}
    # Pull geo label from config if available, falling back to default.
    geo_label = "Lithuania"
    if full_cfg:
        geo_label = (
            (full_cfg.get("search") or {}).get("default_geo_keyword")
            or (full_cfg.get("web_discovery") or {}).get("geo_scope", "Vilnius").title()
            or geo_label
        )
    return {
        "cv_excerpt": cv_context_blob()[:600],
        "top_evidence": (evidence or [])[:5],
        "persona_accept_rate": entry.get("rate"),
        "persona_sent_count": entry.get("sent", 0),
        "geo_label": geo_label,
        "cv_variant": cv_variant,
    }


def supervisor_context(
    row: dict[str, str], *, full_cfg: dict[str, Any]
) -> dict[str, Any]:
    flags = {
        x.strip() for x in str(row.get("company_flags") or "").split(",") if x.strip()
    }
    persona = str(row.get("persona") or "")
    stats = load_persona_stats()
    return {
        "company_history": _company_history(str(row.get("company") or "")),
        "persona_stats": stats.get(persona) or {},
        "rule_score_breakdown": {
            "company_relevance_score": row.get("company_relevance_score"),
            "rank_score_draft": row.get("rank_score_draft"),
            "validation_status": row.get("validation_status"),
        },
        "hard_flags": sorted(flags.intersection(HARD_REJECT_FLAGS)),
        "all_flags": sorted(flags),
    }
