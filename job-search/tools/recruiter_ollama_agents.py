"""Ollama LLM agents for the recruiter pipeline (Qwen single-model stack)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from matching_lib import PROFILES_PATH
from pydantic import BaseModel, Field, field_validator
from recruiter_ollama_client import (
    agent_cfg,
    agent_enabled,
    agent_uses_tools,
    invoke_structured,
    invoke_with_tools,
)
from recruiter_web_research import WebSearchHit

TOOLS = Path(__file__).resolve().parent
JOB_ROOT = TOOLS.parent
CV_DIR = JOB_ROOT / "cv"
PROMPTS_PATH = JOB_ROOT / "linkedin" / "agent_prompts.yaml"

TRACK_SUMMARY = (
    "Candidate tracks: luxury-retail, luxury-retail-lt, operations-management, "
    "it-business. Geography: Vilnius/Lithuania/Baltics. Target hiring leaders in "
    "premium retail, multi-site ops, or IT support — not generic staffing/pharma/finance."
)


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


@lru_cache(maxsize=1)
def _prompts_raw() -> dict[str, Any]:
    if PROMPTS_PATH.is_file():
        try:
            raw = yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8")) or {}
            if isinstance(raw.get("agents"), dict):
                return raw["agents"]
        except Exception:
            pass
    return {}


def agent_system_prompt(agent_name: str, fallback: str) -> str:
    block = _prompts_raw().get(agent_name) or {}
    system = block.get("system")
    if isinstance(system, str) and system.strip():
        return system.strip()
    return fallback


DISCOVERY_SYSTEM = f"""You extract LinkedIn hiring-leader candidates from web search results.
{TRACK_SUMMARY}
Return structured candidates with linkedin.com/in/ profile_url when present in url or snippet.
Skip staffing agencies, pharma, banking, pure sales without hiring signals."""

COMPANY_SYSTEM = f"""You assess whether a company is relevant for outreach in Vilnius/Lithuania hiring network.
{TRACK_SUMMARY}
Flag staffing_only, wrong_sector, geo_mismatch, track_aligned, outreach_exclude_term when applicable.
Never recommend approved for generic staffing-only firms."""

OUTREACH_SYSTEM = """You polish LinkedIn connection notes to be specific and under 280 characters.
Keep first name greeting. Cite their role, company, or region — not generic recruiter phrasing.
Do not mention AI. English unless the draft is Lithuanian."""

SUPERVISOR_SYSTEM = f"""You supervise borderline recruiter outreach rows.
{TRACK_SUMMARY}
Only approve when company and role clearly align. Reject staffing/pharma/wrong sector.
Default to review when uncertain."""


@lru_cache(maxsize=1)
def cv_context_blob() -> str:
    lines: list[str] = []
    if PROFILES_PATH.is_file():
        raw = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
        for slug, block in (raw.get("variants") or {}).items():
            if not isinstance(block, dict):
                continue
            titles = block.get("target_titles") or []
            kws = (block.get("keywords") or [])[:12]
            lines.append(f"{slug}: titles={titles[:4]} keywords={kws}")
            md_name = str(block.get("markdown") or "")
            md_path = CV_DIR / md_name
            if md_path.is_file():
                excerpt = md_path.read_text(encoding="utf-8")[:400].replace("\n", " ")
                lines.append(f"  excerpt: {excerpt[:400]}")
    return "\n".join(lines) if lines else TRACK_SUMMARY


def _hits_payload(hits: list[WebSearchHit]) -> str:
    rows = []
    for idx, hit in enumerate(hits, start=1):
        rows.append(
            {
                "i": idx,
                "title": hit.title,
                "url": hit.url,
                "snippet": (hit.snippet or "")[:250],
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=2)


def extract_discovery_batch(
    hits: list[WebSearchHit],
    *,
    variant_slug: str,
    full_cfg: dict[str, Any],
) -> list[DiscoveryExtraction]:
    if not hits or not agent_enabled(full_cfg, "discovery"):
        return []
    from recruiter_agent_context import discovery_context

    ctx_rows = [
        discovery_context(h, variant_slug=variant_slug, full_cfg=full_cfg) for h in hits
    ]
    system = agent_system_prompt("discovery", DISCOVERY_SYSTEM)
    user = (
        f"CV variant focus: {variant_slug}\n\n"
        f"CV context:\n{cv_context_blob()}\n\n"
        f"Hit context:\n{json.dumps(ctx_rows, ensure_ascii=False)}\n\n"
        f"Search hits:\n{_hits_payload(hits)}"
    )
    batch_cfg = agent_cfg(full_cfg, "discovery")
    if batch_cfg.get("batch_hits", True):
        result = invoke_structured(
            full_cfg, "discovery", system, user, DiscoveryBatchResult
        )
        if result and result.candidates:
            return result.candidates
    out: list[DiscoveryExtraction] = []
    for hit in hits:
        single = invoke_structured(
            full_cfg,
            "discovery",
            system,
            f"Variant: {variant_slug}\nHit:\n{json.dumps({'title': hit.title, 'url': hit.url, 'snippet': hit.snippet[:250]})}",
            DiscoveryExtraction,
        )
        if single:
            out.append(single)
    return out


def analyze_company(
    *,
    company: str,
    headline: str,
    web_blob: str,
    full_cfg: dict[str, Any],
) -> CompanyAnalysis | None:
    if not agent_enabled(full_cfg, "company_analyst"):
        return None
    from recruiter_agent_context import company_context
    from recruiter_agent_validators import validate_company_analysis

    ctx = company_context(
        company=company, headline=headline, web_blob=web_blob, full_cfg=full_cfg
    )
    system = agent_system_prompt("company_analyst", COMPANY_SYSTEM)
    user = (
        f"Company: {company}\n"
        f"Profile headline: {headline}\n\n"
        f"Context:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n\n"
        f"Web evidence:\n{web_blob[:2000]}"
    )
    result = invoke_structured(
        full_cfg, "company_analyst", system, user, CompanyAnalysis
    )
    if not result:
        return None
    ok, _issues = validate_company_analysis(result)
    return result if ok else None


def polish_outreach_note(
    *,
    draft_note: str,
    name: str,
    headline: str,
    company: str,
    persona: str,
    cv_variant: str,
    full_cfg: dict[str, Any],
    profile_url: str = "",
    evidence: list[str] | None = None,
    validation_issues: list[str] | None = None,
) -> OutreachNote | None:
    if not agent_enabled(full_cfg, "outreach_writer"):
        return None
    from recruiter_agent_context import outreach_context
    from recruiter_agent_tools import tools_for_agent
    from recruiter_agent_validators import validate_outreach_note

    ctx = outreach_context(
        name=name,
        headline=headline,
        company=company,
        persona=persona,
        cv_variant=cv_variant,
        evidence=evidence,
        full_cfg=full_cfg,
    )
    system = agent_system_prompt("outreach_writer", OUTREACH_SYSTEM)
    user = (
        f"Draft note: {draft_note}\n"
        f"Name: {name}\nHeadline: {headline}\nCompany: {company}\n"
        f"Persona: {persona}\nCV variant: {cv_variant}\n"
        f"Profile URL: {profile_url}\n\n"
        f"Context:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}"
    )
    if agent_uses_tools(full_cfg, "outreach_writer"):
        tools = tools_for_agent(full_cfg, "outreach_writer")
        result = invoke_with_tools(
            full_cfg,
            "outreach_writer",
            system,
            user,
            OutreachNote,
            tools,
        )
    else:
        result = invoke_structured(
            full_cfg, "outreach_writer", system, user, OutreachNote
        )
    if not result or not result.note.strip():
        return None
    ok, issues = validate_outreach_note(
        result.note, name=name, evidence=result.evidence_cited or headline
    )
    if validation_issues is not None:
        validation_issues.clear()
        validation_issues.extend(issues)
    return result if ok else None


def supervise_row(
    row: dict[str, str], *, full_cfg: dict[str, Any]
) -> SupervisorDecision | None:
    if not agent_enabled(full_cfg, "supervisor"):
        return None
    from recruiter_agent_context import supervisor_context
    from recruiter_agent_tools import tools_for_agent
    from recruiter_agent_validators import validate_supervisor_decision

    agents = (full_cfg.get("llm") or {}).get("agents") or {}
    sup = agents.get("supervisor") or {}
    cfg = full_cfg
    if sup.get("heavy_model") and row.get("_use_heavy_supervisor"):
        cfg = {
            **full_cfg,
            "llm": {
                **(full_cfg.get("llm") or {}),
                "agents": {
                    **agents,
                    "supervisor": {**sup, "model": sup["heavy_model"]},
                },
            },
        }
    ctx = supervisor_context(row, full_cfg=full_cfg)
    system = agent_system_prompt("supervisor", SUPERVISOR_SYSTEM)
    enriched_about = (row.get("enriched_about") or "").strip()
    enriched_role = (row.get("enriched_role_text") or "").strip()
    user_payload: dict[str, Any] = {
        k: row.get(k)
        for k in (
            "name",
            "headline",
            "company",
            "location",
            "validation_status",
            "company_relevance_score",
            "company_rationale",
            "company_flags",
            "rank_score_draft",
            "persona",
            "variant_slug",
        )
    }
    # Surface enriched profile text so the supervisor can judge actual role
    # signals (e.g. "Talent Acquisition Manager — recruits across portfolio")
    # rather than just the company sector.
    if enriched_about:
        user_payload["profile_about_excerpt"] = enriched_about[:800]
    if enriched_role:
        user_payload["profile_role_excerpt"] = enriched_role[:800]
    user_payload["context"] = ctx
    user = json.dumps(user_payload, ensure_ascii=False, indent=2)
    if agent_uses_tools(cfg, "supervisor"):
        tools = tools_for_agent(cfg, "supervisor")
        result = invoke_with_tools(
            cfg, "supervisor", system, user, SupervisorDecision, tools
        )
    else:
        result = invoke_structured(cfg, "supervisor", system, user, SupervisorDecision)
    if not result:
        return None
    ok, _issues = validate_supervisor_decision(result, row)
    return result if ok else None
