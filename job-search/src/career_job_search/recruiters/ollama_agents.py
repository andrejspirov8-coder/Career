"""Ollama LLM agents for the recruiter pipeline (Qwen single-model stack)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import yaml

from career_job_search.core.paths import project_path
from career_job_search.cvs.context import TRACK_SUMMARY, cv_context_blob
from career_job_search.recruiters.agent_models import (
    CompanyAnalysis,
    DiscoveryBatchResult,
    DiscoveryExtraction,
    OutreachNote,
    SupervisorDecision,
)
from career_job_search.recruiters.ollama_client import (
    agent_cfg,
    agent_enabled,
    agent_uses_tools,
    invoke_structured,
    invoke_with_tools,
)
from career_job_search.recruiters.web_models import WebSearchHit

PROMPTS_PATH = project_path("linkedin", "agent_prompts.yaml")


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


def agent_few_shot_messages(agent_name: str) -> list[dict[str, str]]:
    """Convert YAML few_shot entries (input/output pairs) into user/assistant messages.

    Returns an empty list when no few_shot is defined.
    """
    block = _prompts_raw().get(agent_name) or {}
    examples = block.get("few_shot")
    if not examples or not isinstance(examples, list):
        return []
    messages: list[dict[str, str]] = []
    for example in examples:
        if not isinstance(example, dict):
            continue
        inp = example.get("input")
        out = example.get("output")
        if inp is not None and out is not None:
            messages.append({"role": "user", "content": str(inp)})
            messages.append({"role": "assistant", "content": str(out)})
    return messages


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
For HR/talent acquisition contacts at non-retail employers (software, IT, services),
do not name-drop luxury fashion brands from the sender CV; focus on exploring leadership
roles in Vilnius and their hiring/talent work.
Do not mention AI. English unless the draft is Lithuanian."""

SUPERVISOR_SYSTEM = f"""You supervise borderline recruiter outreach rows for the Vilnius/Lithuania hiring network.
{TRACK_SUMMARY}
Target personas the user wants to connect with:
  1. Sector-aligned leaders — luxury/premium retail, multi-site operations, IT support — at companies in those sectors.
  2. Cross-sector HR contacts — in-house recruiters, talent acquisition managers,
     HR business partners, people partners, executive search consultants, hiring managers —
     who happen to work AT a software/tech/services company in Vilnius. These are valuable
     even when their employer is not retail, because they hire across portfolios and have
     network of other HR contacts in the city.
Approve when EITHER condition (1) or (2) holds and the profile is in Vilnius/Lithuania.
Reject when company_flags includes staffing_only, wrong_sector, or outreach_exclude_term,
or when the profile is clearly outside the Baltics, or when the headline/role has no
hiring/recruiting/leadership signal at all.
Default to "review" only when you have no evidence either way."""


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
    from career_job_search.recruiters.agent_context import discovery_context

    ctx_rows = [
        discovery_context(h, variant_slug=variant_slug, full_cfg=full_cfg) for h in hits
    ]
    system = agent_system_prompt("discovery", DISCOVERY_SYSTEM)
    few_shot = agent_few_shot_messages("discovery")
    user = (
        f"CV variant focus: {variant_slug}\n\n"
        f"CV context:\n{cv_context_blob()}\n\n"
        f"Hit context:\n{json.dumps(ctx_rows, ensure_ascii=False)}\n\n"
        f"Search hits:\n{_hits_payload(hits)}"
    )
    batch_cfg = agent_cfg(full_cfg, "discovery")
    if batch_cfg.get("batch_hits", True):
        result = invoke_structured(
            full_cfg,
            "discovery",
            system,
            user,
            DiscoveryBatchResult,
            few_shot=few_shot,
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
            few_shot=few_shot,
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
    from career_job_search.recruiters.agent_context import company_context
    from career_job_search.recruiters.agent_validators import validate_company_analysis

    ctx = company_context(
        company=company, headline=headline, web_blob=web_blob, full_cfg=full_cfg
    )
    system = agent_system_prompt("company_analyst", COMPANY_SYSTEM)
    few_shot = agent_few_shot_messages("company_analyst")
    user = (
        f"Company: {company}\n"
        f"Profile headline: {headline}\n\n"
        f"Context:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n\n"
        f"Web evidence:\n{web_blob[:2000]}"
    )
    result = invoke_structured(
        full_cfg,
        "company_analyst",
        system,
        user,
        CompanyAnalysis,
        few_shot=few_shot,
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
    from career_job_search.recruiters.agent_context import outreach_context
    from career_job_search.recruiters.agent_tools import tools_for_agent
    from career_job_search.recruiters.agent_validators import validate_outreach_note

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
    few_shot = agent_few_shot_messages("outreach_writer")
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
            few_shot=few_shot,
        )
    else:
        result = invoke_structured(
            full_cfg,
            "outreach_writer",
            system,
            user,
            OutreachNote,
            few_shot=few_shot,
        )
    if not result or not result.note.strip():
        return None
    ok, issues = validate_outreach_note(
        result.note,
        name=name,
        evidence=result.evidence_cited or headline,
        company=company,
        cv_variant=cv_variant,
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
    from career_job_search.recruiters.agent_context import supervisor_context
    from career_job_search.recruiters.agent_tools import tools_for_agent
    from career_job_search.recruiters.agent_validators import (
        validate_supervisor_decision,
    )

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
    few_shot = agent_few_shot_messages("supervisor")
    if agent_uses_tools(cfg, "supervisor"):
        tools = tools_for_agent(cfg, "supervisor")
        result = invoke_with_tools(
            cfg,
            "supervisor",
            system,
            user,
            SupervisorDecision,
            tools,
            few_shot=few_shot,
        )
    else:
        result = invoke_structured(
            cfg,
            "supervisor",
            system,
            user,
            SupervisorDecision,
            few_shot=few_shot,
        )
    if not result:
        return None
    ok, _issues = validate_supervisor_decision(result, row)
    return result if ok else None
