"""LLM-enhanced job matching scorer using Ollama local model."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from career_job_search.recruiters.ollama_agents import (
    agent_few_shot_messages,
    agent_system_prompt,
)
from career_job_search.recruiters.ollama_client import (
    agent_enabled,
    invoke_structured,
    llm_enabled,
)

logger = logging.getLogger(__name__)

JOB_SCORER_SYSTEM = """You are a career coach scoring how well a candidate's CV matches a job description.
The candidate has these CV variants: luxury-retail, luxury-retail-lt, operations-management,
operations-management-lt, business-process-operations, it-business.
Geography focus: Vilnius/Lithuania/Baltics/Remote EU.

Analyze the CV against the job requirements and return:
- relevance_0_100: Overall fit score from 0 (no match) to 100 (perfect match)
- rationale: 2-3 sentence explanation of the score
- key_strengths: Top 3 areas where the candidate's CV is a strong match
- key_gaps: Top 3 missing skills or experience from the job description
- transferable_skills: Skills from the CV that apply well to this role even if not explicitly required
- recommendation: "apply" for strong matches (70+), "tailor_cv" for moderate matches (40-69) where CV needs adaptation, "skip" for poor matches (below 40)

Base your score on concrete evidence from both the CV and the job description.
Be critical but fair — consider transferable skills positively."""


class JobMatchScore(BaseModel):
    relevance_0_100: float = Field(ge=0, le=100)
    rationale: str
    key_strengths: list[str]
    key_gaps: list[str]
    transferable_skills: list[str]
    recommendation: str


def score_with_llm(
    config: dict[str, Any],
    opportunity: Any,
    cv_variant_slug: str,
    cv_markdown_path: str,
) -> JobMatchScore | None:
    if not llm_enabled(config) or not agent_enabled(config, "job_scorer"):
        return None
    try:
        from pathlib import Path

        cv_text = Path(cv_markdown_path).read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read CV markdown at %s: %s", cv_markdown_path, exc)
        return None
    system = agent_system_prompt("job_scorer", JOB_SCORER_SYSTEM)
    few_shot = agent_few_shot_messages("job_scorer")
    user = (
        f"Job Title: {opportunity.title}\n"
        f"Company: {opportunity.company}\n"
        f"Location: {opportunity.location}\n"
        f"Description:\n{opportunity.description}\n"
        f"Salary: {opportunity.salary_text}\n"
        f"URL: {opportunity.source_url}\n\n"
        f"CV Variant: {cv_variant_slug}\n"
        f"CV Markdown:\n{cv_text}"
    )
    try:
        from career_job_search.opportunities.qdrant_memory import build_context_for_llm

        memory_context = build_context_for_llm(opportunity)
        if memory_context:
            user += f"\n\n{memory_context}"
    except Exception:
        logger.debug("Qdrant memory context not available")
    return invoke_structured(
        config,
        "job_scorer",
        system,
        user,
        JobMatchScore,
        few_shot=few_shot,
    )


def score_with_rules(
    opportunity: Any,
    keyword_hits: list[str],
    keyword_gaps: list[str],
    fit_score: float,
) -> JobMatchScore:
    relevance = min(100.0, max(0.0, fit_score * 5.0))
    if relevance >= 70:
        recommendation = "apply"
    elif relevance >= 40:
        recommendation = "tailor_cv"
    else:
        recommendation = "skip"
    return JobMatchScore(
        relevance_0_100=round(relevance, 1),
        rationale=(
            f"Keyword-based match score of {fit_score:.1f} ({relevance:.0f}/100). "
            f"Matched {len(keyword_hits)} keyword(s), "
            f"{len(keyword_gaps)} gap(s) identified."
        ),
        key_strengths=keyword_hits[:3] if keyword_hits else [],
        key_gaps=keyword_gaps[:3] if keyword_gaps else [],
        transferable_skills=[],
        recommendation=recommendation,
    )
