"""Opportunity scoring and explanation helpers."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from career_job_search.cvs.matching import (
    PROFILES_PATH,
    keyword_gaps,
    load_profiles,
    match_job_to_variants,
)
from career_job_search.opportunities.eligibility import (
    classify_location_eligibility,
    is_eligible,
)
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityMatch,
    OpportunitySourceKind,
    OpportunityStatus,
    next_action_for_opportunity,
    utc_now_iso,
)
from career_job_search.opportunities.text import (
    clean_opportunity_text,
    extract_deadline,
    extract_salary_text,
)

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
            "technical architect",
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
        # A title hit is much stronger evidence than generic wording in a long
        # description.  This prevents company boilerplate from choosing a role
        # family on its own.
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


def _parse_salary_amounts(salary_text: str) -> list[float]:
    """Extract numeric amounts, treating comma/dot as thousands separators
    when they group exactly three digits (European notation, e.g. ``3,400``)
    and as a decimal point otherwise (e.g. ``3.4``)."""
    amounts: list[float] = []
    for value in re.findall(r"\b\d[\d ]*(?:[.,]\d+)?\b", salary_text):
        if not value.strip():
            continue
        cleaned = value.replace(" ", "")
        try:
            if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", cleaned):
                amounts.append(float(cleaned.replace(",", "").replace(".", "")))
            else:
                amounts.append(float(cleaned.replace(",", ".")))
        except ValueError:
            # Mixed separators (e.g. "1,234.56") are not cleanly parseable;
            # skip rather than crash the whole match.
            continue
    return amounts


def _parse_salary_with_knotation(salary_text: str) -> list[float]:
    """Parse salary amounts that include k/K notation (e.g. ``2.5k``, ``43k EUR``).
    Handles European dot-thousands (2.63 = 2630) and k-notation (2.5k = 2500)."""
    amounts: list[float] = []
    for match in re.finditer(
        r"\b\d+(?:\.\d+)?(?:[.,]\d+)?\s*(?:k|m|K|M)?\b",
        salary_text.lower(),
    ):
        raw_value = match.group(0).replace(" ", "")
        if not raw_value:
            continue
        multiplier = 1.0
        # Check for k/K/m/M suffix
        if raw_value.endswith(("k", "m")):
            multiplier = 1000
            raw_value = raw_value[:-1]
        # Handle European dot-thousands (2.630 = 2630)
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw_value):
            cleaned = raw_value.replace(".", "").replace(",", "")
        else:
            cleaned = raw_value.replace(",", ".")
        try:
            num = float(cleaned) * multiplier
            if num >= 500:
                amounts.append(num)
        except ValueError:
            continue
    return amounts


def salary_score(opportunity: Opportunity) -> float:
    text = f"{opportunity.salary_text} {opportunity.description}".lower()
    if not opportunity.salary_text.strip() and not re.search(
        r"\b(eur|€|salary)\b", text
    ):
        return 0.0
    # Try European dot-thousands (2.63 → 2630), k-notation (2.5k → 2500),
    # and standard comma-thousands (3,400 → 3400) in addition to regular parsing.
    amounts = _parse_salary_amounts(opportunity.salary_text)
    k_amounts = _parse_salary_with_knotation(opportunity.salary_text)
    amounts = sorted(set(amounts + k_amounts))
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
    if _is_role_family_mismatch(
        opportunity,
        chosen_variant=chosen_variant,
        variants=variants,
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
    return _has_hard_title_mismatch(title)


def _has_hard_title_mismatch(title: str) -> bool:
    normalized = clean_opportunity_text(title).casefold()
    if not normalized:
        return False
    if any(signal in normalized for signal in TARGET_TITLE_SIGNALS):
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


def match_opportunity(
    opportunity: Opportunity,
    *,
    variants: dict[str, object] | None = None,
    scoring_config: dict[str, object] | None = None,
) -> Opportunity:
    profiles = variants or load_profiles(PROFILES_PATH)
    workflow_status = opportunity.status
    preserve_workflow_status = workflow_status in {
        OpportunityStatus.APPLIED,
        OpportunityStatus.SKIPPED,
        OpportunityStatus.APPLY_READY,
        OpportunityStatus.FOLLOW_UP,
        OpportunityStatus.EXPIRED,
    }
    previous_eligibility = opportunity.location_eligibility
    clean_description = clean_opportunity_text(opportunity.description)
    if not opportunity.salary_text.strip():
        opportunity.salary_text = extract_salary_text(clean_description)
    if not opportunity.deadline.strip():
        opportunity.deadline = extract_deadline(clean_description)
    eligibility = classify_location_eligibility(opportunity)
    opportunity.location_eligibility = eligibility.eligibility
    opportunity.eligibility_reason = eligibility.reason
    now = utc_now_iso()
    if is_eligible(eligibility) and not opportunity.first_eligible_at:
        first_seen = opportunity.first_seen_at or opportunity.discovered_at
        if (
            previous_eligibility
            in {
                "ineligible",
                "verify_remote",
            }
            or opportunity.source_kind == OpportunitySourceKind.JOB_ALERT
            or first_seen.startswith(now[:10])
        ):
            opportunity.first_eligible_at = now

    result = match_job_to_variants(_parsed_job(opportunity), profiles)
    rec = result["recommendation"]
    chosen = _route_lithuanian_variant(
        str(rec["variant_slug"]),
        opportunity=opportunity,
        variants=profiles,
    )
    ranked = list(result["variants_ranked"])
    selected_index = next(
        (
            index
            for index, row in enumerate(ranked)
            if str(row.get("slug") or row.get("variant_slug") or "") == chosen
        ),
        0,
    )
    selected = ranked.pop(selected_index)
    ranked.sort(
        key=lambda row: (
            float(row.get("primary_score") or 0.0),
            float(row.get("tie_break_score") or 0.0),
        ),
        reverse=True,
    )
    ranked.insert(0, selected)
    runner_up = (
        ranked[1]
        if len(ranked) > 1
        else {"slug": "", "primary_score": 0.0, "tie_break_score": 0.0}
    )
    cv_score = float(selected.get("primary_score") or 0.0)
    runner_up_score = float(runner_up.get("primary_score") or 0.0)
    margin_over_second = max(0.0, round(cv_score - runner_up_score, 4))
    confidence = (
        "clear_winner"
        if cv_score > 0 and margin_over_second >= max(5.0, 0.15 * max(cv_score, 1.0))
        else "tie_review"
    )
    result["variants_ranked"] = ranked
    result["recommendation"] = {
        **rec,
        "variant_slug": chosen,
        "primary_score": cv_score,
        "confidence": confidence,
        "margin_over_second": margin_over_second,
    }
    result["runner_up"] = {
        "variant_slug": str(
            runner_up.get("slug") or runner_up.get("variant_slug") or ""
        ),
        "primary_score": runner_up_score,
    }
    gaps, _notes = keyword_gaps(chosen, clean_description, profiles)
    missing = [token for token, _count in gaps]
    opportunity.evidence.cv_fit_evidence = selected.get("keyword_hits") or []
    opportunity.evidence.risk_flags = risk_flags_for_opportunity(
        opportunity,
        cv_score,
        scoring_config,
        chosen_variant=chosen,
        variants=profiles,
    )
    opportunity.evidence.confidence = 0.85 if confidence == "clear_winner" else 0.55
    loc_score = location_score(opportunity, scoring_config)
    track_score, track_name = role_track_score(opportunity, scoring_config)
    src_score = source_score(opportunity)
    sal_score = salary_score(opportunity)
    due_score = deadline_score(opportunity)
    penalty = risk_penalty(opportunity.evidence.risk_flags)
    fit_score = max(
        0.0,
        cv_score
        + loc_score
        + track_score
        + src_score
        + sal_score
        + due_score
        - penalty,
    )
    opportunity.match = OpportunityMatch(
        best_variant=chosen,
        score=fit_score,
        fit_score=fit_score,
        cv_score=cv_score,
        location_score=loc_score,
        role_track_score=track_score,
        source_score=src_score,
        salary_score=sal_score,
        deadline_score=due_score,
        risk_penalty=penalty,
        role_track=track_name,
        runner_up_variant=str(
            runner_up.get("slug") or runner_up.get("variant_slug") or ""
        ),
        runner_up_score=runner_up_score,
        margin_over_second=margin_over_second,
        confidence=confidence,
        variant_scores=[
            {
                "variant": str(row.get("slug") or row.get("variant_slug") or ""),
                "primary_score": float(row.get("primary_score") or 0.0),
                "tie_break_score": float(row.get("tie_break_score") or 0.0),
                "keyword_hits": list(row.get("keyword_hits") or []),
            }
            for row in result["variants_ranked"]
        ],
        keyword_hits=selected.get("keyword_hits") or [],
        missing_keywords=missing,
        explanation=explanation_for_match(opportunity, result, missing),
    )
    hard_review_flags = {
        "missing_title",
        "missing_company",
        "low_cv_score",
        "possible_scam",
        "duplicate",
        "watchlist_only",
        "link_review_required",
        "needs_live_verification",
        "role_family_mismatch",
        "location_ineligible",
        "remote_eligibility_unverified",
    }
    if preserve_workflow_status:
        opportunity.status = workflow_status
    elif any(flag in hard_review_flags for flag in opportunity.evidence.risk_flags):
        opportunity.status = OpportunityStatus.REVIEW
    elif confidence == "clear_winner" and fit_score >= 16 and len(missing) < 8:
        opportunity.status = OpportunityStatus.APPLY_READY
    else:
        opportunity.status = OpportunityStatus.MATCHED
    opportunity.next_action = next_action_for_opportunity(opportunity)
    return opportunity


def _route_lithuanian_variant(
    chosen: str,
    *,
    opportunity: Opportunity,
    variants: dict[str, object],
) -> str:
    if chosen.endswith("-lt") or not _looks_lithuanian(opportunity):
        return chosen
    candidate = f"{chosen}-lt"
    return candidate if candidate in variants else chosen


def _looks_lithuanian(opportunity: Opportunity) -> bool:
    text = f"{opportunity.title} {opportunity.description}".casefold()
    if any(char in text for char in "ąčęėįšųūž"):
        return True
    tokens = set(re.findall(r"[a-z]+", text))
    return bool(
        tokens
        & {
            "darbo",
            "ieskome",
            "klientu",
            "komandos",
            "parduotuvės",
            "vadovas",
            "vadove",
            "vilniuje",
        }
    )


def match_opportunities(
    opportunities: list[Opportunity],
    *,
    variants: dict[str, object] | None = None,
    scoring_config: dict[str, object] | None = None,
) -> list[Opportunity]:
    profiles = variants or load_profiles(PROFILES_PATH)
    return [
        match_opportunity(row, variants=profiles, scoring_config=scoring_config)
        for row in opportunities
    ]
