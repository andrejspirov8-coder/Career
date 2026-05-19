"""Post-LLM validation gates for Ollama agent outputs."""

from __future__ import annotations

import re

from recruiter_ollama_agents import CompanyAnalysis, SupervisorDecision

_GENERIC_EVIDENCE = frozenset(
    {
        "linkedin profile",
        "your profile",
        "your work",
        "your background",
        "relevant leadership",
        "hiring network",
    }
)

_FORBIDDEN_NOTE_TOKENS = re.compile(
    r"\b(AI|assistant|chatgpt|gpt|llm)\b|[^\x00-\x7F]", re.I
)


def validate_outreach_note(
    note: str, *, name: str, evidence: str = ""
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    text = " ".join((note or "").split())
    if len(text) > 280:
        issues.append("note_too_long")
    if len(text) < 20:
        issues.append("note_too_short")
    first = (name or "").split()[0].lower() if name.strip() else ""
    if first and first not in text.lower():
        issues.append("missing_first_name")
    if _FORBIDDEN_NOTE_TOKENS.search(text):
        issues.append("forbidden_token_or_emoji")
    ev = (evidence or "").lower().strip()
    if ev in _GENERIC_EVIDENCE or len(ev) < 4:
        issues.append("generic_evidence")
    return not issues, issues


def validate_company_analysis(analysis: CompanyAnalysis) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if analysis.recommended_status not in {"approved", "review", "reject"}:
        issues.append("invalid_status")
    if not 0 <= analysis.relevance_0_100 <= 100:
        issues.append("score_out_of_range")
    return not issues, issues


def validate_supervisor_decision(
    decision: SupervisorDecision, row: dict[str, str]
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if decision.action not in {"approved", "review", "reject"}:
        issues.append("invalid_action")
    flags = {
        x.strip() for x in str(row.get("company_flags") or "").split(",") if x.strip()
    }
    hard = {"outreach_exclude_term", "wrong_sector", "staffing_only"}
    if decision.action == "approved" and flags.intersection(hard):
        issues.append("approve_with_hard_flag")
    score = float(row.get("company_relevance_score") or 0)
    approve_threshold = 60.0
    if decision.action == "approved" and score < approve_threshold:
        issues.append("approve_below_threshold")
    return not issues, issues
