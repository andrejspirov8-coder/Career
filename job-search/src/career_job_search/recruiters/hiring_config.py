"""Hiring-network configuration, persona classification, and candidate parsing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

from career_job_search.integrations.linkedin.paths import DEFAULT_LINKEDIN_CONFIG
from career_job_search.recruiters import matching as rm
from career_job_search.recruiters.hiring_models import PersonaDecision, ProfileCandidate

_LEADERSHIP_PERSONAS = frozenset(
    {"retail_area_leader", "store_director", "operations_leader", "it_business_leader"}
)
_HIRING_VALIDATION_PERSONAS = frozenset(
    {"recruiter_hr", "hiring_manager", "executive_search"}
)
_PRESERVE_HARD_FLAGS = frozenset(
    {"staffing_only", "wrong_sector", "outreach_exclude_term"}
)
_DISCOVERY_PERSONA_PRESERVED = "discovery_persona_preserved"
_GENERIC_HIRING_TERMS = frozenset({"director", "vadovas", "manager", "country manager"})
_GENERIC_EVIDENCE_TERMS = frozenset(
    {
        "recruiter",
        "hr manager",
        "human resources",
        "talent acquisition",
        "hiring and leadership",
        "your field",
        "hiring",
    }
)

_VARIANT_CONTEXT_TERMS: dict[str, tuple[str, ...]] = {
    "luxury-retail": (
        "luxury",
        "premium",
        "fashion",
        "retail",
        "boutique",
        "apranga",
        "massimo dutti",
        "zara",
        "lpp",
        "hugo boss",
        "michael kors",
        "store",
    ),
    "luxury-retail-lt": (
        "luxury",
        "premium",
        "fashion",
        "retail",
        "boutique",
        "apranga",
        "massimo dutti",
        "prabang",
        "mazmen",
        "parduotuv",
        "michael kors",
        "store",
    ),
    "operations-management": (
        "operations",
        "operation",
        "multi-site",
        "multi site",
        "area manager",
        "regional manager",
        "district manager",
        "project management",
        "team lead",
        "store operations",
    ),
    "it-business": (
        "it",
        "technical",
        "technology",
        "service desk",
        "service delivery",
        "it support",
        "business analyst",
        "software",
        "systems",
        "guidehouse",
        "adform",
        "vinted",
        "nfq",
        "ignitis",
    ),
}

VISION_ALLOWED_LABELS: set[str] = {
    "profile_loaded",
    "connect_visible",
    "pending_visible",
    "login_wall",
    "checkpoint",
    "captcha",
    "unusual_activity",
    "unknown",
}


def default_hiring_network_config() -> dict[str, Any]:
    """Default config used when YAML does not define hiring_network."""
    return {
        "auto_send_threshold": 76.0,
        "queue_review_threshold": 58.0,
        "weights": {
            "cv_fit": 0.35,
            "hiring_authority": 0.25,
            "company_sector": 0.20,
            "geography": 0.10,
            "personalization": 0.05,
            "history": 0.05,
        },
        "persona_weights": {
            "recruiter_hr": 82,
            "executive_search": 90,
            "hiring_manager": 85,
            "retail_area_leader": 96,
            "store_director": 90,
            "operations_leader": 86,
            "it_business_leader": 84,
            "low_relevance": 0,
        },
        "company_priority_terms": [
            "michael kors",
            "michael page",
            "premium",
            "luxury",
            "fashion",
            "retail",
            "boutique",
            "baltics",
            "lithuania",
        ],
        "geography_terms": ["vilnius", "lithuania", "lietuva", "baltics", "kaunas"],
        "persona_terms": {
            "recruiter_hr": [
                "recruiter",
                "talent acquisition",
                "headhunter",
                "human resources",
                "hr manager",
                "hr business partner",
                "people partner",
                "people & culture",
                "personalo",
                "įdarbinim",
            ],
            "retail_area_leader": [
                "area manager",
                "regional manager",
                "district manager",
                "cluster manager",
                "head of retail",
                "retail director",
                "regiono vadov",
            ],
            "store_director": [
                "store director",
                "store manager",
                "boutique manager",
                "flagship manager",
                "parduotuvės direktor",
            ],
            "operations_leader": [
                "operations director",
                "director of operations",
                "operations manager",
                "general manager",
                "multi-site",
                "multi site",
            ],
            "it_business_leader": [
                "it support manager",
                "service delivery manager",
                "service desk manager",
                "business analyst lead",
                "it operations manager",
                "technical support manager",
            ],
            "executive_search": [
                "executive search",
                "retained search",
                "search consultant",
                "leadership advisory",
            ],
            "hiring_manager": [
                "hiring manager",
                "country manager retail",
                "director of retail",
                "director of stores",
                "retail hiring manager",
            ],
        },
        "persona_note_templates": {
            "recruiter_hr": (
                "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
                "Would value connecting given your work in {evidence}."
            ),
            "hiring_manager": (
                "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
                "Your {evidence} background looked relevant, and I would value connecting."
            ),
            "retail_area_leader": (
                "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
                "Your {evidence} work stood out, and I would value connecting."
            ),
            "store_director": (
                "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
                "Your {evidence} experience looked relevant, and I would value connecting."
            ),
            "operations_leader": (
                "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
                "Your {evidence} work looked relevant, and I would value connecting."
            ),
            "it_business_leader": (
                "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
                "Your {evidence} work looked relevant, and I would value connecting."
            ),
        },
    }


def load_workflow_config(config_path: Path = DEFAULT_LINKEDIN_CONFIG) -> dict[str, Any]:
    """Load hiring_network config from YAML and merge it over defaults."""
    cfg = default_hiring_network_config()
    if yaml is None or not config_path.exists():
        return cfg
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return cfg
    hn = raw.get("hiring_network") or {}
    if not isinstance(hn, dict):
        return cfg
    return deep_merge(cfg, hn)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_full_linkedin_cfg() -> dict[str, Any]:
    import os
    import sys

    if yaml is None or not DEFAULT_LINKEDIN_CONFIG.exists():
        return {}
    cfg = yaml.safe_load(DEFAULT_LINKEDIN_CONFIG.read_text(encoding="utf-8")) or {}
    if os.environ.get("JOB_SEARCH_NO_LLM") == "1" or "unittest" in sys.modules:
        cfg = {**cfg, "llm": {**(cfg.get("llm") or {}), "enabled": False}}
    return cfg


def industry_hit(blob_lower: str, cfg: dict[str, Any], cv_variant: str = "") -> bool:
    """Track-aligned industry signal for persona gating."""
    track = [str(x) for x in cfg.get("track_aligned_company_terms") or []]
    if not track:
        track = [str(x) for x in cfg.get("company_priority_terms") or []]
    strong = [
        t
        for t in track
        if t not in ("retail", "lithuania", "baltics", "lietuva", "kaunas")
    ]
    if _term_hits(blob_lower, strong):
        return True
    if _term_hits(blob_lower, track) and not _staffing_only_retail(blob_lower):
        return True
    if cv_variant:
        sector_map = rm._merged_sector_map(None)
        phrases = sector_map.get(cv_variant) or []
        return any(p.lower().strip() in blob_lower for p in phrases if len(p) >= 3)
    return False


def _staffing_only_retail(blob_lower: str) -> bool:
    return ("staffing" in blob_lower or "recruitment agency" in blob_lower) and not any(
        t in blob_lower for t in ("luxury", "premium", "fashion", "boutique", "prabang")
    )


def _term_hits(blob_lower: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        t = str(term).strip().lower()
        if not t:
            continue
        if " " in t or "-" in t:
            ok = t in blob_lower
        else:
            ok = bool(re.search(rf"\b{re.escape(t)}\b", blob_lower))
        if ok and t not in hits:
            hits.append(t)
    return hits


def classify_persona(
    candidate: ProfileCandidate, cfg: dict[str, Any]
) -> PersonaDecision:
    """Classify likely hiring-process role from profile text."""
    blob = candidate.text_blob().lower()
    persona_terms = cfg.get("persona_terms") or {}
    scores: dict[str, list[str]] = {}
    for persona, terms in persona_terms.items():
        if not isinstance(terms, list):
            continue
        hits = _term_hits(blob, [str(x) for x in terms])
        if hits:
            scores[str(persona)] = hits

    sales_only = rm.is_sales_only_without_hiring_signal(blob, None)
    if sales_only and not scores:
        return PersonaDecision(
            persona="low_relevance",
            hiring_authority_score=0,
            confidence=0.15,
            evidence=[],
            risk_flags=["sales_only_no_hiring_signal"],
        )

    if rm.profile_has_outreach_exclude(
        blob, {"hiring_network": cfg, "recruiter_matching": cfg}
    ):
        return PersonaDecision(
            persona="low_relevance",
            hiring_authority_score=0,
            confidence=0.2,
            evidence=[],
            risk_flags=["outreach_exclude_term"],
        )

    priority = [
        "retail_area_leader",
        "store_director",
        "operations_leader",
        "it_business_leader",
        "executive_search",
        "recruiter_hr",
        "hiring_manager",
    ]
    picked = ""
    for persona in priority:
        if persona not in scores:
            continue
        if persona in _LEADERSHIP_PERSONAS and not industry_hit(blob, cfg):
            continue
        picked = persona
        break

    if not picked and "hiring_manager" in scores:
        hm_hits = scores["hiring_manager"]
        if not all(h in _GENERIC_HIRING_TERMS for h in hm_hits):
            picked = "hiring_manager"

    if not picked and "recruiter_hr" in scores:
        picked = "recruiter_hr"

    if not picked:
        return PersonaDecision(
            persona="low_relevance",
            hiring_authority_score=0,
            confidence=0.2,
            evidence=[],
            risk_flags=["no_hiring_network_signal"],
        )

    hits = scores[picked][:6]
    risk_flags: list[str] = []

    if (
        picked == "hiring_manager"
        and hits
        and all(h in _GENERIC_HIRING_TERMS for h in hits)
    ):
        return PersonaDecision(
            persona="low_relevance",
            hiring_authority_score=0,
            confidence=0.2,
            evidence=hits,
            risk_flags=["generic_director_only"],
        )

    base_score = float((cfg.get("persona_weights") or {}).get(picked, 70))
    extra = min(8.0, max(0, len(hits) - 1) * 2.0)
    confidence = min(0.98, 0.68 + 0.08 * len(hits))
    return PersonaDecision(
        persona=picked,  # type: ignore[arg-type]
        hiring_authority_score=min(100.0, base_score + extra),
        confidence=confidence,
        evidence=hits,
        risk_flags=risk_flags,
    )


def _parse_company_flags(raw: Any) -> set[str]:
    return {x.strip() for x in str(raw or "").split(",") if x.strip()}


def _candidate_in_preserve_geo(
    candidate: ProfileCandidate, cfg: dict[str, Any]
) -> bool:
    blob = f"{candidate.location} {candidate.headline}".lower()
    geo_terms = cfg.get("geography_terms") or [
        "vilnius",
        "lithuania",
        "lietuva",
        "baltics",
        "kaunas",
    ]
    return bool(_term_hits(blob, [str(t) for t in geo_terms]))


def _automation_cfg() -> dict[str, Any]:
    return _load_full_linkedin_cfg().get("automation") or {}


def resolve_persona(
    candidate: ProfileCandidate,
    cfg: dict[str, Any],
    *,
    discovery_persona: str = "",
    validation_status: str = "",
    company_flags: str = "",
) -> PersonaDecision:
    """Re-classify profile text; preserve discovery CSV persona when rank would drop to low_relevance."""
    fresh = classify_persona(candidate, cfg)
    auto = _automation_cfg()
    if not bool(auto.get("preserve_discovery_persona", True)):
        return fresh
    if fresh.persona != "low_relevance":
        return fresh

    preserve_set = {
        str(p).strip().lower()
        for p in (
            auto.get("preserve_discovery_personas") or list(_HIRING_VALIDATION_PERSONAS)
        )
        if str(p).strip()
    }
    flags = _parse_company_flags(company_flags)
    if flags.intersection(_PRESERVE_HARD_FLAGS):
        return fresh

    requires_geo = bool(auto.get("preserve_requires_geo", True))
    if requires_geo and not _candidate_in_preserve_geo(candidate, cfg):
        return fresh

    persona_key = (discovery_persona or "").strip().lower()
    if persona_key not in preserve_set:
        return fresh
    status = (validation_status or "").strip().lower()
    if status == "reject":
        return fresh

    base_score = float((cfg.get("persona_weights") or {}).get(persona_key, 70))
    return PersonaDecision(
        persona=persona_key,  # type: ignore[arg-type]
        hiring_authority_score=base_score,
        confidence=0.65,
        evidence=[_DISCOVERY_PERSONA_PRESERVED],
        risk_flags=[],
    )


def candidate_from_scout_record(record: dict[str, Any]) -> ProfileCandidate:
    text_parts = [
        str(record.get(k) or "")
        for k in (
            "headline",
            "name",
            "recruiter_name",
            "company",
            "company_guess",
            "location",
            "canonical_id",
            "tier",
            "action",
            "reason",
            "search_variant_slug",
            "variant_slug_best",
            "variant_slug",
            "search_intent",
            "scraped_about_excerpt",
            "about",
            "role_text",
            "top_signals",
            "note_preview_trim",
            "note_preview",
            "validation_status",
            "company_relevance_score",
            "company_flags",
            "company_rationale",
        )
        if str(record.get(k) or "").strip()
    ]
    if str(record.get("canonical_id") or "").startswith("recruiter:") or record.get(
        "recruiter_name"
    ):
        text_parts.append("recruiter")
    text = "\n".join(text_parts)
    return ProfileCandidate(
        profile_url=str(record.get("profile_url") or ""),
        name=str(record.get("name") or record.get("recruiter_name") or ""),
        headline=str(record.get("headline") or ""),
        company=str(record.get("company_guess") or record.get("company") or ""),
        location=str(record.get("location") or ""),
        scraped_text=text,
        search_variant_slug=str(
            record.get("search_variant_slug")
            or record.get("variant_slug_best")
            or record.get("variant_slug")
            or ""
        ),
        source_backend=str(record.get("source_backend") or ""),
    )
