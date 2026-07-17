"""Post-model validation gates for recruiter agent outputs."""

from __future__ import annotations

import re

from career_job_search.recruiters.agent_models import (
    CompanyAnalysis,
    SupervisorDecision,
)

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

# Luxury brand keywords to check for brand-dropping at non-retail companies.
_LUXURY_BRAND_TERMS = re.compile(
    r"\b(?:"
    r"prada|versace|gucci|harrods|michael kors|louis vuitton|dior|chanel|"
    r"fendi|burberry|givenchy|armani|valentino|balenciaga|saint laurent|"
    r"ysl|herm[eè]s|cartier|tiffany|bottega|loewe|moncler|"
    r"zegna|boss|tom ford|ralph lauren|calvin klein"
    r")\b",
    re.I,
)

# Company terms that signal the target is in the retail/luxury/fashion sector.
_RETAIL_SECTOR_SIGNALS = re.compile(
    r"\b(?:"
    r"luxury|premium|retail|fashion|boutique|apparel|"
    r"mažmen|prabang|concession|store|shop"
    r")\b",
    re.I,
)


def validate_outreach_note(
    note: str,
    *,
    name: str,
    evidence: str = "",
    company: str = "",
    cv_variant: str = "",
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
    # evidence_cited should contain at least some text referenced in the note.
    if ev and len(ev) >= 4:
        cited_words = ev.split()
        actionable = [w for w in cited_words if len(w) > 4 and w.isalpha()]
        if actionable and not any(w in text.lower() for w in actionable):
            issues.append("evidence_not_cited_in_note")
    # Brand-drop check: if company is non-retail, luxury brand mentions are flagged.
    if _check_brand_drop(note, company):
        issues.append("brand_drop_at_non_retail")
    return not issues, issues


def _check_brand_drop(note: str, company: str) -> bool:
    """Return True if the note name-drops luxury brands for a non-retail company."""
    company_text = (company or "").lower().strip()
    if not company_text:
        return False  # No company context — can't judge
    if _RETAIL_SECTOR_SIGNALS.search(company_text):
        return False  # Company is retail/luxury — brand mentions are fine
    return bool(_LUXURY_BRAND_TERMS.search(note))


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
