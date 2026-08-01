"""Opportunity scoring helpers extracted from matching.py."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from career_job_search.opportunities.eligibility import (
    classify_location_eligibility,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunitySourceKind,
)
from career_job_search.opportunities.text import (
    clean_opportunity_text,
)

logger = logging.getLogger(__name__)

DEFAULT_PRIORITY_REGIONS = [
    "vilnius",
    "lithuania",
    "lietuva",
    "baltics",
    "remote eu",
    "remote europe",
    "europe",
    "emea",
    "uk",
    "germany",
    "netherlands",
    "nordics",
]

DEFAULT_ROLE_TRACKS = [
    {
        "name": "business_process_operations",
        "keywords": [
            "business process",
            "process improvement",
            "operations analyst",
            "workflow",
            "implementation",
            "stakeholder",
        ],
    },
    {
        "name": "customer_operations",
        "keywords": [
            "customer operations",
            "customer support",
            "member support",
            "sla",
            "quality",
            "support operations",
        ],
    },
    {
        "name": "retail_operations",
        "keywords": [
            "retail operations",
            "store operations",
            "stock control",
            "inventory",
            "kpi",
            "area manager",
        ],
    },
    {
        "name": "luxury_retail_leadership",
        "keywords": [
            "luxury",
            "boutique",
            "clienteling",
            "visual merchandising",
            "premium retail",
        ],
    },
]

TECHNICAL_TITLE_MISMATCH_TERMS = (
    "data engineer",
    "software engineer",
    "backend engineer",
    "front end engineer",
    "frontend engineer",
    "full stack engineer",
    "platform engineer",
    "infrastructure engineer",
    "machine learning engineer",
    "devops engineer",
    "site reliability engineer",
    "solutions architect",
    "technical architect",
    "engineering manager",
)

TARGET_TITLE_SIGNALS = (
    "operations",
    "operational",
    "business analyst",
    "process analyst",
    "process coordinator",
    "customer operations",
    "customer support",
    "customer service",
    "customer success",
    "customer experience",
    "member support",
    "implementation",
    "onboarding",
    "service desk",
    "helpdesk",
    "application support",
    "technical support",
    "retail manager",
    "store manager",
    "boutique manager",
    "area manager",
    "district manager",
    "regional manager",
    "office manager",
    "front office",
    "guest services",
    "account manager",
    "delivery coordinator",
    "operations coordinator",
    "operacij",
    "veiklos vadov",
    "veiklos analitik",
    "verslo analitik",
    "procesų",
    "procesu",
    "klientų aptarn",
    "klientu aptarn",
    "parduotuvės vadov",
    "parduotuvės direkt",
    "parduotuves vadov",
    "mažmenin",
    "mazmenin",
    "padalinio vadov",
    "komandos vadov",
    "pardavimų vadov",
    "pardavimu vadov",
)

HARD_MISMATCH_TITLE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "recruiting_or_hr",
        (
            "recruiter",
            "recruiting",
            "talent acquisition",
            "talent partner",
            "human resources",
            "people partner",
        ),
    ),
    (
        "software_or_engineering",
        (
            "business intelligence",
            "data analyst",
            "data lifecycle",
            "data scientist",
            "engineer",
            "software engineer",
            "data engineer",
            "developer",
            "devops",
            "site reliability",
            "solutions architect",
            "solution architect",
            "technical architect",
            "technical program manager",
            "digital workplace technical lead",
            "network administrator",
            "software project lead",
            "l2 technical support",
            "level 2 technical support",
            "deployment architect",
            "security engineer",
            "security lead",
            "engineering manager",
            "programuotoj",
            "inžinier",
            "inzinier",
        ),
    ),
    (
        "finance_or_accounting",
        (
            "accountant",
            "accounting",
            "financial controller",
            "financial controlling",
            "finance manager",
            "financial analyst",
            "finance analyst",
            "cost accountant",
            "investment accounting",
            "credit risk",
            "buhalter",
            "apskait",
        ),
    ),
    (
        "marketing_product_or_creative",
        (
            "creative",
            "marketing",
            "marketing manager",
            "marketing project",
            "product manager",
            "product owner",
            "product marketing",
            "e-commerce",
            "ecommerce",
            "creative designer",
            "graphic designer",
            "copywriter",
            "growth manager",
        ),
    ),
    (
        "sales_only",
        (
            "account executive",
            "business development",
            "head of sales",
            "partnership",
            "pricing",
            "sales director",
            "sales development",
            "business development representative",
            "sales representative",
            "pardavimų trener",
            "pardavimu trener",
        ),
    ),
    (
        "specialist_profession",
        (
            "legal counsel",
            "forestry",
            "forest officer",
            "raf operations",
            "fraud specialist",
            "risk process manager",
            "sanctions compliance",
            "compliance officer",
            "hr project manager",
            "hr services coordinator",
            "rewards manager",
            "internal communications",
            "immigration",
            "lawyer",
            "clinical",
            "medical doctor",
            "scientist",
            "construction engineer",
            "statybos inžinier",
            "statybos inzinier",
        ),
    ),
)

DERIVED_RISK_FLAGS = {
    "language_requirement_risk",
    "location_ineligible",
    "low_cv_score",
    "missing_company",
    "missing_title",
    "possible_scam",
    "remote_eligibility_unverified",
    "role_family_mismatch",
    "vague_role",
    "visa_location_risk",
    "weak_location_fit",
}


def _parsed_job(opportunity: Opportunity) -> dict[str, Any]:
    clean_description = clean_opportunity_text(opportunity.description)
    return {
        "title": opportunity.title,
        "company": opportunity.company,
        "url": opportunity.source_url,
        "source": opportunity.source,
        "job_id": opportunity.opportunity_id,
        "body": clean_description,
        "job_file": None,
        "title_boost_region": f"{opportunity.title} {opportunity.company}".lower(),
    }


def _config_list(
    config: dict[str, object] | None, key: str, fallback: list[object]
) -> list[object]:
    if not config:
        return fallback
    value = config.get(key)
    return value if isinstance(value, list) else fallback


def _priority_regions(scoring_config: dict[str, object] | None) -> list[str]:
    configured = _config_list(
        scoring_config, "priority_regions", DEFAULT_PRIORITY_REGIONS
    )
    return [str(item).lower() for item in configured if str(item).strip()]


def _role_tracks(scoring_config: dict[str, object] | None) -> list[dict[str, object]]:
    configured = _config_list(scoring_config, "role_tracks", DEFAULT_ROLE_TRACKS)
    return [item for item in configured if isinstance(item, dict)]


def _opportunity_text(opportunity: Opportunity) -> str:
    return clean_opportunity_text(
        " ".join(
            [
                opportunity.title,
                opportunity.company,
                opportunity.location,
                opportunity.remote_policy,
                opportunity.description,
                opportunity.salary_text,
            ]
        )
    ).lower()


def _has_priority_location(
    opportunity: Opportunity, scoring_config: dict[str, object] | None
) -> bool:
    text = _opportunity_text(opportunity)
    return any(region in text for region in _priority_regions(scoring_config))


def location_score(
    opportunity: Opportunity, scoring_config: dict[str, object] | None
) -> float:
    eligibility = classify_location_eligibility(opportunity).eligibility
    if eligibility == "eligible_vilnius":
        return 6.0
    if eligibility in {"eligible_lt_remote", "eligible_eu_remote"}:
        return 5.0
    return 0.0


def role_track_score(
    opportunity: Opportunity, scoring_config: dict[str, object] | None
) -> tuple[float, str]:
    if _has_hard_title_mismatch(opportunity.title):
        return 0.0, ""
    title = clean_opportunity_text(opportunity.title).casefold()
    description = clean_opportunity_text(opportunity.description).casefold()
    best_score = 0.0
    best_track = ""
    for track in _role_tracks(scoring_config):
        keywords = track.get("keywords") or []
        title_hits = sum(1 for keyword in keywords if str(keyword).casefold() in title)
        description_hits = sum(
            1 for keyword in keywords if str(keyword).casefold() in description
        )
        try:
            weight = float(track.get("weight") or 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        score = min(
            8.0,
            float(title_hits * 4 + description_hits) * max(0.0, weight),
        )
        if score > best_score:
            best_score = score
            best_track = str(track.get("name") or "")
    return best_score, best_track


def source_score(opportunity: Opportunity) -> float:
    if opportunity.source_kind == OpportunitySourceKind.ATS:
        return 3.0
    if opportunity.source_kind == OpportunitySourceKind.COMPANY_SITE:
        return 2.5
    if opportunity.source_kind == OpportunitySourceKind.JOB_ALERT:
        return 2.5
    if opportunity.source_kind == OpportunitySourceKind.MANUAL_INBOX:
        return 2.0
    if opportunity.source_kind == OpportunitySourceKind.RECRUITER:
        return 1.5
    return 1.0


def salary_score(opportunity: Opportunity) -> float:
    if not opportunity.salary_text.strip():
        return 0.0
    amounts = [
        float(value.replace(" ", "").replace(",", "."))
        for value in re.findall(r"\b\d[\d ]*(?:[.,]\d+)?\b", opportunity.salary_text)
        if value.strip()
    ]
    monthly_amounts = [amount for amount in amounts if amount >= 500]
    if not monthly_amounts:
        return 1.0
    return 1.0 + min(max(monthly_amounts) / 5000.0, 1.5)


def deadline_score(opportunity: Opportunity) -> float:
    if not opportunity.deadline:
        return 0.0
    try:
        deadline = date.fromisoformat(opportunity.deadline)
    except ValueError:
        return 0.0
    return 1.0 if deadline >= date.today() else -2.0


def risk_penalty(flags: list[str]) -> float:
    weights = {
        "possible_scam": 8.0,
        "role_family_mismatch": 8.0,
        "low_cv_score": 5.0,
        "weak_location_fit": 3.0,
        "needs_live_verification": 3.0,
        "language_requirement_risk": 2.0,
        "visa_location_risk": 3.0,
        "vague_role": 2.0,
        "duplicate": 2.0,
        "likely_closed": 10.0,
    }
    return sum(weights.get(flag, 0.0) for flag in flags)


def risk_flags_for_opportunity(
    opportunity: Opportunity,
    score: float,
    scoring_config: dict[str, object] | None = None,
    *,
    chosen_variant: str = "",
    variants: dict[str, object] | None = None,
    selected_negative_hits: list[str] | None = None,
) -> list[str]:
    flags = [
        flag
        for flag in opportunity.evidence.risk_flags
        if flag not in DERIVED_RISK_FLAGS
    ]
    if not opportunity.title.strip():
        flags.append("missing_title")
    if not opportunity.company.strip():
        flags.append("missing_company")
    if len(opportunity.description.strip()) < 80:
        flags.append("vague_role")
    if score < 8:
        flags.append("low_cv_score")
    eligibility = classify_location_eligibility(opportunity)
    if eligibility.eligibility == "ineligible":
        flags.append("location_ineligible")
    elif eligibility.eligibility == "verify_remote":
        flags.append("remote_eligibility_unverified")
    language_risks = (
        "french speaking",
        "german speaking",
        "spanish speaking",
        "fluent french",
        "fluent german",
        "native french",
        "native german",
    )
    if any(token in _opportunity_text(opportunity) for token in language_risks):
        flags.append("language_requirement_risk")
    visa_risks = (
        "us only",
        "u.s. only",
        "must be based in the us",
        "must be based in united states",
        "right to work in the uk",
        "visa sponsorship is not available",
    )
    if any(token in _opportunity_text(opportunity) for token in visa_risks):
        flags.append("visa_location_risk")
    suspicious = ("telegram", "whatsapp only", "pay to apply", "crypto only")
    if any(token in opportunity.description.lower() for token in suspicious):
        flags.append("possible_scam")
    if selected_negative_hits or _is_role_family_mismatch(
        opportunity, chosen_variant=chosen_variant, variants=variants
    ):
        flags.append("role_family_mismatch")
    return list(dict.fromkeys(flag for flag in flags if flag))


def _is_role_family_mismatch(
    opportunity: Opportunity,
    *,
    chosen_variant: str,
    variants: dict[str, object] | None,
) -> bool:
    title = clean_opportunity_text(opportunity.title).casefold()
    if not title:
        return False
    if _has_hard_title_mismatch(title):
        return True
    target_titles: list[str] = []
    for slug, profile in (variants or {}).items():
        if slug != chosen_variant and not isinstance(profile, dict):
            continue
        if isinstance(profile, dict):
            target_titles.extend(
                str(item).casefold() for item in profile.get("target_titles") or []
            )
    if any(target and target in title for target in target_titles):
        return False
    return False


def _has_hard_title_mismatch(title: str) -> bool:
    normalized = clean_opportunity_text(title).casefold()
    if not normalized:
        return False
    return any(
        term in normalized
        for _family, terms in HARD_MISMATCH_TITLE_PATTERNS
        for term in terms
    )


def explanation_for_match(
    opportunity: Opportunity, result: dict[str, Any], missing_keywords: list[str]
) -> dict[str, str]:
    rec = result["recommendation"]
    hits = (
        ", ".join(result["variants_ranked"][0].get("keyword_hits") or [])
        or "available role text"
    )
    missing = (
        ", ".join(missing_keywords[:5]) if missing_keywords else "no standout gaps"
    )
    role_mismatch = "role_family_mismatch" in opportunity.evidence.risk_flags
    location_ineligible = "location_ineligible" in opportunity.evidence.risk_flags
    if role_mismatch:
        decision = (
            "Skip by default: the job title is outside the supported CV role families."
        )
    elif location_ineligible:
        decision = (
            "Skip by default: the stated location is not eligible from Lithuania."
        )
    else:
        decision = "Review locally before applying; no auto-apply is available."
    return {
        "why_this_role": f"{opportunity.title or 'This role'} at {opportunity.company or 'the company'} matched using {hits}.",
        "why_this_cv": f"Best CV variant is {rec['variant_slug']} with score {rec['primary_score']}.",
        "what_is_missing": missing,
        "why_apply_review_or_skip": decision,
    }
