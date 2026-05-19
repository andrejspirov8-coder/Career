#!/usr/bin/env python3
"""Agentic hiring-network workflow for LinkedIn outreach.

The workflow keeps analysis deterministic and structured. Agent-like nodes
classify, match, rank, and write notes; the existing Playwright dispatcher is
the only component that can click LinkedIn controls.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

import linkedin_selectors as lis
import recruiter_match as rm
from matching_lib import PROFILES_PATH, load_profiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from recruiter_discovery_csv import read_validated_rows
from recruiter_linkedin_paths import (
    ACTION_PLAN_JSONL,
    CANDIDATES_DISCOVERY_CSV,
    CANDIDATES_VALIDATED_CSV,
    DEFAULT_LINKEDIN_CONFIG,
    HIRING_NETWORK_ACTION_PLAN_JSONL,
    HIRING_NETWORK_RUN_STATE_JSON,
    RECRUITERS_CSV,
)

try:
    import linkedin_recruiter_bot as bot
except ModuleNotFoundError:
    bot = None


Persona = Literal[
    "recruiter_hr",
    "executive_search",
    "hiring_manager",
    "retail_area_leader",
    "store_director",
    "operations_leader",
    "it_business_leader",
    "low_relevance",
]

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

SendTier = Literal["auto_send", "queue_review", "skip"]
Decision = Literal["approved", "review", "skip"]
ScreenState = Literal[
    "profile_loaded",
    "connect_visible",
    "pending_visible",
    "login_wall",
    "checkpoint",
    "captcha",
    "unusual_activity",
    "unknown",
]

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


class ProfileCandidate(BaseModel):
    """Profile facts scraped from LinkedIn or loaded from a scout action plan."""

    model_config = ConfigDict(extra="forbid")

    profile_url: str
    name: str = ""
    headline: str = ""
    company: str = ""
    location: str = ""
    scraped_text: str = ""
    search_variant_slug: str = ""
    source_backend: str = ""

    @field_validator("profile_url")
    @classmethod
    def validate_linkedin_profile_url(cls, value: str) -> str:
        canon = lis.canonical_profile_url(value)
        if not canon:
            raise ValueError("profile_url must be a LinkedIn /in/ profile URL")
        return canon

    def text_blob(self) -> str:
        return "\n".join(
            x
            for x in (
                self.name,
                self.headline,
                self.company,
                self.location,
                self.scraped_text,
            )
            if x.strip()
        )


class PersonaDecision(BaseModel):
    """Hiring-process persona classification."""

    model_config = ConfigDict(extra="forbid")

    persona: Persona
    hiring_authority_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    risk_flags: list[str] = Field(default_factory=list, max_length=8)


class CvMatchDecision(BaseModel):
    """Best CV variant for a candidate profile."""

    model_config = ConfigDict(extra="forbid")

    best_cv_variant: str
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    runner_up_variant: str = ""
    margin_over_second: float = 0.0


class HistorySignals(BaseModel):
    """Outcome-derived feedback for future ranking."""

    model_config = ConfigDict(extra="forbid")

    sent_count: int = 0
    accepted_count: int = 0
    reply_count: int = 0
    interview_count: int = 0

    def score(self) -> float:
        if self.sent_count <= 0:
            return 50.0
        accept = self.accepted_count / self.sent_count
        reply = self.reply_count / self.sent_count
        interview = self.interview_count / self.sent_count
        return max(
            0.0, min(100.0, 100.0 * (0.4 * accept + 0.4 * reply + 0.2 * interview))
        )


class RankedInvite(BaseModel):
    """Final structured record approved, queued, or skipped before dispatch."""

    model_config = ConfigDict(extra="forbid")

    candidate: ProfileCandidate
    persona: PersonaDecision
    cv_match: CvMatchDecision
    rank_score: float = Field(ge=0, le=100)
    send_tier: SendTier
    note: str
    risk_flags: list[str] = Field(default_factory=list, max_length=12)
    decision: Decision
    note_reason: str = ""

    @field_validator("note")
    @classmethod
    def validate_note_length(cls, value: str) -> str:
        if len(value) > 280:
            raise ValueError("note must be 280 characters or fewer")
        return value

    @model_validator(mode="after")
    def validate_decision_tier_consistency(self) -> "RankedInvite":
        if self.decision == "approved" and self.send_tier != "auto_send":
            raise ValueError("approved invites must use send_tier=auto_send")
        if self.decision == "skip" and self.send_tier != "skip":
            raise ValueError("skipped invites must use send_tier=skip")
        return self

    def to_action_record(self) -> dict[str, Any]:
        return {
            "schema": "hiring_network_invite_v1",
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "profile_url": self.candidate.profile_url,
            "name": self.candidate.name,
            "headline": self.candidate.headline,
            "company": self.candidate.company,
            "location": self.candidate.location,
            "persona": self.persona.persona,
            "persona_confidence": round(self.persona.confidence, 4),
            "hiring_authority_score": round(self.persona.hiring_authority_score, 4),
            "cv_variant": self.cv_match.best_cv_variant,
            "cv_score": round(self.cv_match.score, 4),
            "cv_confidence": round(self.cv_match.confidence, 4),
            "rank_score": round(self.rank_score, 4),
            "send_tier": self.send_tier,
            "decision": self.decision,
            "risk_flags": self.risk_flags,
            "persona_evidence": self.persona.evidence,
            "cv_evidence": self.cv_match.evidence,
            "note": self.note,
            "note_reason": self.note_reason,
            "source_backend": self.candidate.source_backend,
        }


class RunState(BaseModel):
    """Serializable workflow state."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: str = Field("hiring_network_run_state_v1", alias="schema")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )
    queue: list[RankedInvite] = Field(default_factory=list)
    sent_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    audit_records: list[dict[str, Any]] = Field(default_factory=list)


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


def _variant_context_hits(candidate: ProfileCandidate, variant_slug: str) -> list[str]:
    variant_slug = (variant_slug or "").strip()
    terms = list(_VARIANT_CONTEXT_TERMS.get(variant_slug) or ())
    if variant_slug == "luxury-retail-lt":
        terms.extend(_VARIANT_CONTEXT_TERMS["luxury-retail"])
    blob = candidate.text_blob().lower()
    hits = _term_hits(blob, terms)
    return list(dict.fromkeys(hits))


def _clean_evidence_excerpt(text: str, max_chars: int = 72) -> str:
    clean = re.sub(r"\s+", " ", text).strip(" .,:;")
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip(" ,.;:") + "..."


def match_candidate_to_cv(
    candidate: ProfileCandidate, cfg: dict[str, Any]
) -> CvMatchDecision:
    """Match a candidate profile to the best CV variant using existing scorer."""
    try:
        result = rm.match_recruiter_profile(
            headline=candidate.headline or candidate.name or "LinkedIn profile",
            name=candidate.name,
            profile_url=candidate.profile_url,
            company=candidate.company,
            about=candidate.scraped_text,
            role_text="",
            location=candidate.location,
            recruiter_cfg={"recruiter_matching": {"sector_beats_cv_min_score": 6}},
        )
        rec = result.get("recommendation") or {}
        meta = result.get("recruiter_meta") or {}
        ranked = result.get("variants_ranked") or []
        best = str(
            rec.get("variant_slug") or candidate.search_variant_slug or "luxury-retail"
        )
        raw_score = float(rec.get("primary_score") or 0.0)
        score = max(0.0, min(100.0, raw_score * 5.0))
        margin = float(rec.get("margin_over_second") or 0.0)
        conf_raw = str(rec.get("confidence") or "")
        confidence = 0.86 if conf_raw == "clear_winner" else 0.64
        if margin >= 4:
            confidence = min(0.96, confidence + 0.08)
        evidence = [
            x.strip()
            for x in str(meta.get("top_signals") or "").split(",")
            if x.strip()
        ]
        if not evidence and ranked:
            hits = ranked[0].get("keyword_hits") or []
            evidence = [str(x) for x in hits[:5]]

        source_variant = candidate.search_variant_slug.strip()
        source_hits = _variant_context_hits(candidate, source_variant)
        if source_variant and source_hits:
            best = source_variant
            score = max(score, min(100.0, 68.0 + len(source_hits[:5]) * 5.0))
            confidence = max(confidence, 0.78 if len(source_hits) >= 2 else 0.68)
            evidence = list(dict.fromkeys(source_hits[:5] + evidence))[:6]

        full_cfg = _load_full_linkedin_cfg()
        try:
            from recruiter_ollama_embed import blend_cv_score

            score = blend_cv_score(score, candidate.text_blob(), best, full_cfg)
        except Exception:
            pass

        return CvMatchDecision(
            best_cv_variant=best,
            score=score,
            confidence=confidence,
            evidence=evidence[:6],
            runner_up_variant=str(rec.get("runner_up_slug") or ""),
            margin_over_second=margin,
        )
    except Exception:
        fallback = candidate.search_variant_slug or "luxury-retail"
        return CvMatchDecision(
            best_cv_variant=fallback,
            score=0,
            confidence=0.1,
            evidence=[],
            runner_up_variant="",
            margin_over_second=0,
        )


def company_sector_score(candidate: ProfileCandidate, cfg: dict[str, Any]) -> float:
    blob = candidate.text_blob().lower()
    track = [str(x) for x in cfg.get("track_aligned_company_terms") or []]
    if not track:
        track = [str(x) for x in cfg.get("company_priority_terms", [])]
    hits = _term_hits(blob, track)
    if not hits:
        return 25.0
    if _staffing_only_retail(blob):
        return 32.0
    strong = [h for h in hits if h not in ("retail", "lithuania", "baltics")]
    return min(100.0, 40.0 + len(strong) * 16.0 + len(hits) * 4.0)


def geography_score(candidate: ProfileCandidate, cfg: dict[str, Any]) -> float:
    blob = candidate.text_blob().lower()
    hits = _term_hits(blob, [str(x) for x in cfg.get("geography_terms", [])])
    abroad_markers = (
        "united kingdom",
        "uk ",
        " london",
        "poland",
        "germany",
        "usa",
        "united states",
        "dubai",
        "warsaw",
    )
    abroad = any(m in blob for m in abroad_markers)
    geo_mode = str(cfg.get("geo_required") or "soft").lower()
    if not hits:
        if abroad and geo_mode == "hard":
            return 10.0
        if abroad and geo_mode == "soft":
            return 28.0
        return 35.0
    if any(x in hits for x in ("vilnius", "lithuania", "lietuva")):
        return 100.0
    return min(90.0, 55.0 + 15.0 * len(hits))


def personalization_score(
    candidate: ProfileCandidate, persona: PersonaDecision, cv: CvMatchDecision
) -> float:
    score = 30.0
    if candidate.name.strip():
        score += 25.0
    if persona.evidence:
        score += 25.0
    if cv.evidence:
        score += 15.0
    if candidate.location.strip():
        score += 5.0
    return min(100.0, score)


def first_name(name: str) -> str:
    return rm.first_name_from_display(name)


def cv_focus_label(variant_slug: str) -> str:
    labels = {
        "luxury-retail": "premium retail leadership",
        "luxury-retail-lt": "premium retail leadership",
        "operations-management": "operations leadership",
        "it-business": "IT support and business-analysis",
    }
    return labels.get(variant_slug, "relevant leadership")


def geo_label(candidate: ProfileCandidate) -> str:
    blob = f"{candidate.location} {candidate.scraped_text} {candidate.headline}".lower()
    if "vilnius" in blob:
        return "Vilnius"
    if "lithuania" in blob or "lietuva" in blob:
        return "Lithuania"
    if "baltic" in blob:
        return "the Baltics"
    return "Lithuania"


def compact_evidence(
    candidate: ProfileCandidate,
    persona: PersonaDecision,
    cv: CvMatchDecision,
) -> str:
    headline = _clean_evidence_excerpt(candidate.headline)
    if headline and headline.lower() not in _GENERIC_EVIDENCE_TERMS:
        return headline

    phrase = rm.evidence_phrase_for_outreach(
        headline=candidate.headline,
        company=candidate.company,
        about=candidate.scraped_text,
        signals_csv=", ".join(cv.evidence),
        persona_evidence=(persona.evidence[0] if persona.evidence else ""),
    )
    if phrase.lower().strip() in _GENERIC_EVIDENCE_TERMS and cv.evidence:
        return _clean_evidence_excerpt(", ".join(cv.evidence[:3]))
    return phrase


def note_evidence_is_generic(evidence: str) -> bool:
    el = evidence.lower().strip()
    return el in _GENERIC_EVIDENCE_TERMS or len(el) < 4


def write_personalized_note(
    candidate: ProfileCandidate,
    persona: PersonaDecision,
    cv: CvMatchDecision,
    cfg: dict[str, Any],
) -> tuple[str, str]:
    templates = cfg.get("persona_note_templates") or {}
    blob = candidate.text_blob().lower()
    template_key = persona.persona
    if persona.persona == "recruiter_hr" and not industry_hit(blob, cfg):
        template_key = "recruiter_hr_cross_sector"
    template = str(
        templates.get(template_key)
        or templates.get(persona.persona)
        or templates.get("hiring_manager")
        or ""
    )
    if not template:
        template = (
            "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
            "Would value connecting given your work in {evidence}."
        )
    evidence = compact_evidence(candidate, persona, cv)
    note = template.format(
        first_name=first_name(candidate.name),
        cv_focus=cv_focus_label(cv.best_cv_variant),
        geo=geo_label(candidate),
        evidence=evidence,
    )
    note = re.sub(r"\s+", " ", note).strip()
    if len(note) > 280:
        note = note[:277].rstrip(" ,.;:") + "..."
    reason = f"{persona.persona}:{evidence}:{cv.best_cv_variant}"
    try:
        from recruiter_ollama_agents import polish_outreach_note
        from recruiter_ollama_client import agent_enabled

        full_cfg = _load_full_linkedin_cfg()
        if agent_enabled(full_cfg, "outreach_writer"):
            llm_issues: list[str] = []
            polished = polish_outreach_note(
                draft_note=note,
                name=candidate.name,
                headline=candidate.headline,
                company=candidate.company,
                persona=persona.persona,
                cv_variant=cv.best_cv_variant,
                full_cfg=full_cfg,
                profile_url=candidate.profile_url,
                evidence=cv.evidence,
                validation_issues=llm_issues,
            )
            if polished and polished.note.strip():
                candidate_note = polished.note.strip()
                evidence_token = (polished.evidence_cited or evidence).strip()
                note = candidate_note
                if len(note) > 280:
                    note = note[:277].rstrip(" ,.;:") + "..."
                reason = (
                    f"{persona.persona}:{evidence_token}:{cv.best_cv_variant}:llm_note"
                )
            elif llm_issues:
                reason = f"{reason}:llm_rejected:{','.join(llm_issues)}"
    except Exception:
        pass
    return note, reason


def rank_candidate(
    candidate: ProfileCandidate,
    persona: PersonaDecision,
    cv: CvMatchDecision,
    cfg: dict[str, Any],
    history: HistorySignals,
    *,
    validated_company_score: float | None = None,
) -> float:
    weights = cfg.get("weights") or {}
    history_score = history.score()
    history_boost = 1.0
    full_cfg = _load_full_linkedin_cfg()
    if bool((full_cfg.get("automation") or {}).get("use_persona_stats", False)):
        try:
            from recruiter_persona_stats import load_persona_stats, persona_boost_factor

            history_boost = persona_boost_factor(persona.persona, load_persona_stats())
        except Exception:
            history_boost = 1.0
    company_sector = company_sector_score(candidate, cfg)
    if validated_company_score is not None:
        company_sector = max(company_sector, validated_company_score)
    components = {
        "cv_fit": cv.score,
        "hiring_authority": persona.hiring_authority_score,
        "company_sector": company_sector,
        "geography": geography_score(candidate, cfg),
        "personalization": personalization_score(candidate, persona, cv),
        "history": history_score * history_boost,
    }
    total_weight = sum(float(weights.get(k, 0.0)) for k in components) or 1.0
    score = (
        sum(float(weights.get(k, 0.0)) * v for k, v in components.items())
        / total_weight
    )
    return round(max(0.0, min(100.0, score)), 4)


def _parse_company_relevance_score(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def apply_validation_rank_adjustments(
    rank_score: float,
    *,
    validation_status: str,
    company_relevance_score: float | None,
    persona: PersonaDecision,
) -> tuple[float, set[str]]:
    """Boost rank from company validation; soften hiring skip for approved HR personas."""
    full_cfg = _load_full_linkedin_cfg()
    auto = full_cfg.get("automation") or {}
    if not bool(auto.get("use_validation_boost", True)):
        return rank_score, set()

    status = (validation_status or "").strip().lower()
    softened: set[str] = set()
    score = rank_score
    boost_approved = float(auto.get("validation_boost_approved") or 8)
    boost_review = float(auto.get("validation_boost_review") or 4)
    soften_min = float(auto.get("validation_soften_hiring_min_score") or 60)

    if status == "approved":
        score += boost_approved
        if (
            company_relevance_score is not None
            and company_relevance_score >= soften_min
            and persona.persona in _HIRING_VALIDATION_PERSONAS
        ):
            softened.add("no_hiring_network_signal")
    elif status == "review" and company_relevance_score is not None:
        if company_relevance_score >= float(
            (full_cfg.get("company_validation") or {}).get("review_threshold") or 40
        ):
            score += boost_review

    if _DISCOVERY_PERSONA_PRESERVED in persona.evidence:
        softened.add("low_hiring_relevance")
        if status == "review":
            softened.add("no_hiring_network_signal")

    return round(max(0.0, min(100.0, score)), 4), softened


def build_ranked_invite(
    candidate: ProfileCandidate,
    *,
    cfg: dict[str, Any],
    history: HistorySignals,
    already_contacted: bool,
    pending_visible: bool,
    validation_status: str = "",
    company_relevance_score: float | None = None,
    discovery_persona: str = "",
    company_flags: str = "",
) -> RankedInvite:
    persona = resolve_persona(
        candidate,
        cfg,
        discovery_persona=discovery_persona,
        validation_status=validation_status,
        company_flags=company_flags,
    )
    cv = match_candidate_to_cv(candidate, cfg)
    rank_score = rank_candidate(
        candidate,
        persona,
        cv,
        cfg,
        history,
        validated_company_score=company_relevance_score,
    )
    rank_score, softened_skips = apply_validation_rank_adjustments(
        rank_score,
        validation_status=validation_status,
        company_relevance_score=company_relevance_score,
        persona=persona,
    )
    if (
        _DISCOVERY_PERSONA_PRESERVED in persona.evidence
        and persona.persona in _HIRING_VALIDATION_PERSONAS
    ):
        if not industry_hit(candidate.text_blob().lower(), cfg):
            softened_skips.add("low_cv_fit")
    note, note_reason = write_personalized_note(candidate, persona, cv, cfg)

    risk_flags: list[str] = []
    risk_flags.extend(persona.risk_flags)
    if already_contacted:
        risk_flags.append("already_contacted")
    if pending_visible:
        risk_flags.append("pending_invitation")
    if persona.persona == "low_relevance":
        risk_flags.append("low_hiring_relevance")
    if cv.score < 35:
        risk_flags.append("low_cv_fit")
    if persona.confidence < 0.55 or cv.confidence < 0.50:
        risk_flags.append("low_confidence")

    evidence_token = note_reason.split(":", 2)[1] if note_reason.count(":") >= 2 else ""
    if note_evidence_is_generic(evidence_token):
        risk_flags.append("note_quality_generic")

    hard_skip_flags = frozenset(
        {
            "already_contacted",
            "pending_invitation",
            "low_hiring_relevance",
            "sales_only_no_hiring_signal",
            "no_hiring_network_signal",
            "no_industry_signal_for_leadership",
            "generic_director_only",
            "outreach_exclude_term",
            "low_cv_fit",
        }
    )

    review_threshold = float(cfg.get("queue_review_threshold", 58.0))
    auto = _automation_cfg()
    if persona.persona == "recruiter_hr":
        review_threshold = float(
            auto.get("recruiter_hr_queue_review_threshold") or review_threshold
        )

    if any(f in hard_skip_flags for f in risk_flags if f not in softened_skips):
        send_tier: SendTier = "skip"
        decision: Decision = "skip"
    elif rank_score >= float(cfg.get("auto_send_threshold", 76.0)):
        if "note_quality_generic" in risk_flags or "low_confidence" in risk_flags:
            send_tier = "queue_review"
            decision = "review"
        else:
            send_tier = "auto_send"
            decision = "approved"
    elif rank_score >= review_threshold:
        send_tier = "queue_review"
        decision = "review"
    else:
        send_tier = "skip"
        decision = "skip"
        risk_flags.append("rank_below_review_threshold")

    return RankedInvite(
        candidate=candidate,
        persona=persona,
        cv_match=cv,
        rank_score=rank_score,
        send_tier=send_tier,
        note=note,
        risk_flags=list(dict.fromkeys(risk_flags)),
        decision=decision,
        note_reason=note_reason,
    )


def read_action_plan_records(path: Path) -> list[dict[str, Any]]:
    """Read either true JSONL or a legacy JSON array saved with .jsonl suffix."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history_by_variant(
    csv_path: Path = RECRUITERS_CSV,
) -> dict[str, HistorySignals]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    if not csv_path.exists():
        return {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            variant = (row.get("variant_slug") or "").strip()
            if not variant:
                continue
            if (row.get("status") or "").strip() == "sent":
                buckets[variant]["sent"] += 1
            if (row.get("accepted_at") or "").strip():
                buckets[variant]["accepted"] += 1
            if (row.get("reply_at") or "").strip():
                buckets[variant]["reply"] += 1
            if (row.get("interview_at") or "").strip():
                buckets[variant]["interview"] += 1
    return {
        variant: HistorySignals(
            sent_count=counts["sent"],
            accepted_count=counts["accepted"],
            reply_count=counts["reply"],
            interview_count=counts["interview"],
        )
        for variant, counts in buckets.items()
    }


def read_contacted_urls(csv_path: Path = RECRUITERS_CSV) -> set[str]:
    if not csv_path.exists():
        return set()
    contacted: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            status = (row.get("status") or "").strip()
            if status not in {"sent", "skipped_pending"}:
                continue
            canon = lis.canonical_profile_url(row.get("profile_url") or "")
            if canon:
                contacted.add(canon)
    return contacted


def build_ranked_plan_from_records(
    records: list[dict[str, Any]],
    *,
    cfg: dict[str, Any],
    contacted_urls: set[str] | None = None,
    history_by_variant: dict[str, HistorySignals] | None = None,
) -> list[RankedInvite]:
    contacted = contacted_urls or set()
    history_map = history_by_variant or {}
    latest_by_url: dict[str, dict[str, Any]] = {}
    for record in records:
        try:
            candidate = candidate_from_scout_record(record)
        except ValueError:
            continue
        latest_by_url[candidate.profile_url] = record

    invites: list[RankedInvite] = []
    for record in latest_by_url.values():
        candidate = candidate_from_scout_record(record)
        hist = history_map.get(candidate.search_variant_slug) or HistorySignals()
        invite = build_ranked_invite(
            candidate,
            cfg=cfg,
            history=hist,
            already_contacted=candidate.profile_url in contacted,
            pending_visible=str(record.get("status") or "") == "skipped_pending",
            validation_status=str(record.get("validation_status") or ""),
            company_relevance_score=_parse_company_relevance_score(
                record.get("company_relevance_score")
            ),
            discovery_persona=str(record.get("discovery_persona") or ""),
            company_flags=str(record.get("company_flags") or ""),
        )
        invites.append(invite)

    invites.sort(
        key=lambda x: (-x.rank_score, x.candidate.name.lower(), x.candidate.profile_url)
    )
    return invites


def classify_screen_state_from_text(text: str) -> ScreenState:
    blob = text.lower()
    if "captcha" in blob or "prove you're human" in blob or "prove youre human" in blob:
        return "captcha"
    if (
        "checkpoint" in blob
        or "security verification" in blob
        or "verify your identity" in blob
    ):
        return "checkpoint"
    if "unusual activity" in blob or "temporarily restricted" in blob:
        return "unusual_activity"
    if ("sign in" in blob and "password" in blob) or "login" in blob:
        return "login_wall"
    if "pending" in blob and "invitation" in blob:
        return "pending_visible"
    if "invite" in blob and "connect" in blob:
        return "connect_visible"
    if "profile" in blob or "experience" in blob or "about" in blob:
        return "profile_loaded"
    return "unknown"


def dependency_status() -> dict[str, bool]:
    deps = {
        "pydantic": True,
        "langgraph": importlib.util.find_spec("langgraph") is not None,
        "playwright": importlib.util.find_spec("playwright") is not None,
        "yaml": importlib.util.find_spec("yaml") is not None,
    }
    return deps


def build_langgraph_workflow(stage: str = "all") -> Any:
    """Build the LangGraph workflow for the three-agent pipeline."""
    from recruiter_graph_workflow import build_langgraph_workflow as build_graph

    return build_graph(stage)  # type: ignore[arg-type]


def cmd_preflight(args: argparse.Namespace) -> int:
    deps = dependency_status()
    print("Hiring-network preflight")
    for name, ok in deps.items():
        print(f"{name}: {'ok' if ok else 'missing'}")
    try:
        _ = load_profiles(PROFILES_PATH)
        print(f"CV profiles: ok ({PROFILES_PATH})")
    except Exception as exc:
        print(f"CV profiles: error ({exc})")
    legacy_records = read_action_plan_records(Path(args.source_action_plan))
    print(f"Source action plan readable records: {len(legacy_records)}")
    if bot is not None:
        try:
            limits = {}
            if yaml is not None and DEFAULT_LINKEDIN_CONFIG.exists():
                raw = (
                    yaml.safe_load(DEFAULT_LINKEDIN_CONFIG.read_text(encoding="utf-8"))
                    or {}
                )
                limits = raw.get("limits") or {}
            print(f"Effective invite cap: {bot.effective_daily_invite_cap(limits)}")
        except Exception as exc:
            print(f"Effective invite cap: unavailable ({exc})")
    try:
        from recruiter_ollama_client import health_check, llm_enabled

        full = _load_full_linkedin_cfg()
        if llm_enabled(full):
            ok, msg = health_check(str((full.get("llm") or {}).get("base_url") or ""))
            print(f"Ollama: {'ok' if ok else 'warn'} ({msg})")
    except Exception as exc:
        print(f"Ollama: unavailable ({exc})")
    return 0 if all(deps.values()) else 2


def cmd_rank(args: argparse.Namespace) -> int:
    cfg = load_workflow_config(Path(args.config))
    records = read_action_plan_records(Path(args.source_action_plan))
    invites = build_ranked_plan_from_records(
        records,
        cfg=cfg,
        contacted_urls=read_contacted_urls(RECRUITERS_CSV),
        history_by_variant=load_history_by_variant(RECRUITERS_CSV),
    )
    action_records = [invite.to_action_record() for invite in invites]
    write_jsonl(Path(args.output), action_records)
    state = RunState(queue=invites, audit_records=action_records[:50])
    HIRING_NETWORK_RUN_STATE_JSON.write_text(
        state.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    counts = Counter(invite.send_tier for invite in invites)
    print(
        f"Wrote {args.output} with {len(invites)} ranked profile(s): "
        f"auto_send={counts['auto_send']} queue_review={counts['queue_review']} skip={counts['skip']}"
    )
    for invite in invites[: min(5, len(invites))]:
        print(
            f"- {invite.send_tier} score={invite.rank_score:.1f} "
            f"{invite.persona.persona} {invite.cv_match.best_cv_variant} "
            f"{invite.candidate.name or invite.candidate.profile_url}"
        )
    return 0


def _run_scout(args: argparse.Namespace) -> int:
    cli = [
        sys.executable,
        str(Path(__file__).resolve().parent / "recruiter_orchestrate.py"),
        "--config",
        str(args.config),
        "scout",
        "--headed" if args.headed else "--no-headed",
        "--action-plan",
        str(args.source_action_plan),
    ]
    if args.browser_channel:
        cli.extend(["--browser-channel", args.browser_channel])
    if args.variant:
        cli.extend(["--variant", args.variant])
    return subprocess.call(cli)


def cmd_daily(args: argparse.Namespace) -> int:
    if args.skip_scout:
        scout_rc = 0
    else:
        scout_rc = _run_scout(args)
    if scout_rc != 0:
        return scout_rc
    rank_rc = cmd_rank(args)
    if rank_rc != 0 or args.dry_run or not args.auto_send:
        return rank_rc
    return cmd_dispatch(args)


def automation_cfg(full_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = full_cfg if full_cfg is not None else _load_full_linkedin_cfg()
    block = cfg.get("automation") or {}
    return block if isinstance(block, dict) else {}


def apply_full_auto_graph_args(args: argparse.Namespace) -> None:
    """Turn on live send + auto-approve when --full-auto is set."""
    if not getattr(args, "full_auto", False):
        return
    args.dry_run = False
    args.auto_approve_review = True
    if args.max is None:
        auto = automation_cfg()
        args.max = int(auto.get("max_dispatch") or 5)
    if getattr(args, "only_new", None) is None:
        args.only_new = True
    if getattr(args, "fresh_run", None) is None:
        args.fresh_run = True


def _resolve_only_new(
    only_new: bool | None, *, tier: str, full_cfg: dict[str, Any]
) -> bool:
    if only_new is not None:
        return only_new
    if tier == "full_auto":
        return True
    return bool(automation_cfg(full_cfg).get("only_new", False))


def _polish_note_for_dispatch(row: dict[str, Any]) -> tuple[str, str]:
    """Last-mile LLM polish so every live send uses a personalized note."""
    note = re.sub(r"\s+", " ", str(row.get("note") or "")).strip()
    reason = str(row.get("note_reason") or "")
    if ":llm_note" in reason:
        return note[:280], reason

    full_cfg = _load_full_linkedin_cfg()
    try:
        from recruiter_ollama_agents import polish_outreach_note
        from recruiter_ollama_client import agent_enabled

        if not agent_enabled(full_cfg, "outreach_writer"):
            return note[:280], reason
        polished = polish_outreach_note(
            draft_note=note,
            name=str(row.get("name") or ""),
            headline=str(row.get("headline") or ""),
            company=str(row.get("company") or ""),
            persona=str(row.get("persona") or "hiring_manager"),
            cv_variant=str(row.get("cv_variant") or "luxury-retail"),
            full_cfg=full_cfg,
        )
        if not polished or not polished.note.strip():
            return note[:280], reason
        evidence = (polished.evidence_cited or "").strip()
        new_note = polished.note.strip()
        if len(new_note) > 280:
            new_note = new_note[:277].rstrip(" ,.;:") + "..."
        persona = str(row.get("persona") or "hiring_manager")
        cv = str(row.get("cv_variant") or "luxury-retail")
        return new_note, f"{persona}:{evidence or 'llm'}:{cv}:llm_note"
    except Exception:
        return note[:280], reason


def _approved_invites_from_plan(
    path: Path,
    *,
    tier: str,
    max_profiles: int | None,
    only_new: bool = False,
    apply_stub_guard: bool = True,
) -> list[dict[str, Any]]:
    from recruiter_dispatch_guard import is_stub_or_empty_row, load_already_sent_urls

    rows = read_action_plan_records(path)
    full_cfg = _load_full_linkedin_cfg()
    auto = automation_cfg(full_cfg)
    include_queue = bool(auto.get("include_queue_review"))
    already_sent = load_already_sent_urls() if only_new else set()
    approved: list[dict[str, Any]] = []
    for row in rows:
        send_tier = str(row.get("send_tier") or "")
        decision = str(row.get("decision") or "")
        if tier == "full_auto":
            if send_tier == "auto_send" and decision == "approved":
                pass
            elif include_queue and send_tier == "queue_review":
                pass
            else:
                continue
        else:
            if decision != "approved":
                continue
            if tier and tier != "all" and send_tier != tier:
                continue
        if apply_stub_guard:
            skip, _reason = is_stub_or_empty_row(row)
            if skip:
                url = str(row.get("profile_url") or row.get("name") or "")
                print(f"Skipped (stub/empty): {url}")
                continue
        if only_new:
            url = lis.canonical_profile_url(row.get("profile_url") or "")
            if url and url in already_sent:
                print(f"Skipped (already sent): {url}")
                continue
        approved.append(row)
        if max_profiles is not None and len(approved) >= max_profiles:
            break
    return approved


def cmd_dispatch(args: argparse.Namespace) -> int:
    tier = str(getattr(args, "tier", "auto_send") or "auto_send")
    full_cfg = _load_full_linkedin_cfg()
    only_new = _resolve_only_new(
        getattr(args, "only_new", None), tier=tier, full_cfg=full_cfg
    )
    approved = _approved_invites_from_plan(
        Path(args.output),
        tier=tier,
        max_profiles=args.max,
        only_new=only_new,
    )
    if not approved:
        raise SystemExit("No approved invites to dispatch.")
    if getattr(args, "dry_run", False):
        print(
            f"DRY RUN: {len(approved)} approved invite(s) would be dispatched "
            f"from {Path(args.output)}"
        )
        for idx, row in enumerate(approved, start=1):
            note, _ = _polish_note_for_dispatch(row)
            print(
                f"{idx}. score={row.get('rank_score')} persona={row.get('persona')} "
                f"cv={row.get('cv_variant')} name={row.get('name') or row.get('profile_url')}"
            )
            print(f"   note: {note[:280]}")
        return 0

    if bot is None:
        raise SystemExit(
            "Playwright dispatcher unavailable: install requirements.txt first."
        )
    raw_cfg = bot.load_config(Path(args.config))
    queued: list[tuple[str, str]] = []
    planned: dict[str, dict[str, Any]] = {}
    auto = automation_cfg(_load_full_linkedin_cfg())
    full_cfg = _load_full_linkedin_cfg()
    try:
        from recruiter_ollama_client import agent_enabled, llm_enabled

        llm_notes_required = bool(
            auto.get("require_llm_note")
            and llm_enabled(full_cfg)
            and agent_enabled(full_cfg, "outreach_writer")
        )
    except Exception:
        llm_notes_required = bool(auto.get("require_llm_note"))
    for row in approved:
        note, note_reason = _polish_note_for_dispatch(row)
        if llm_notes_required and ":llm_note" not in note_reason:
            print(
                f"Skipping (no LLM note): {row.get('name') or row.get('profile_url')}"
            )
            continue
        url = lis.canonical_profile_url(row.get("profile_url") or "")
        variant = str(row.get("cv_variant") or "")
        if not url or not variant:
            continue
        queued.append((url, variant))
        planned[url] = {
            "note": note,
            "persona": row.get("persona") or "",
            "rank_score": row.get("rank_score") or "",
            "profile_confidence": row.get("persona_confidence") or "",
            "safety_decision": row.get("decision") or "",
            "note_reason": note_reason,
        }
    if not queued:
        raise SystemExit("No dispatchable invites after LLM note polish.")
    dispatch_args = argparse.Namespace(
        headed=args.headed,
        dry_run=getattr(args, "dry_run", False),
        scout_jsonl_only=False,
        config=Path(args.config),
        max_connections_override=None,
        variant_filter=None,
        browser_channel=args.browser_channel,
    )
    return bot.run_linked_in_campaign_backend(
        dispatch_args,
        raw_cfg,
        queued_override=queued,
        skip_discovery=True,
        planned_invites=planned,
    )


def cmd_report(args: argparse.Namespace) -> int:
    if getattr(args, "persona_stats", False):
        from recruiter_persona_stats import write_persona_stats

        stats = write_persona_stats()
        print("Persona accept-rate stats (pipeline/persona_stats.json)")
        if not stats:
            print("  (no data yet — run followup after sends)")
            return 0
        print(f"{'Persona':<28} {'Sent':>6} {'Acc':>6} {'Rate':>7}")
        print("-" * 52)
        for persona in sorted(stats.keys()):
            block = stats[persona]
            print(
                f"{persona:<28} {block.get('sent', 0):>6} "
                f"{block.get('accepted', 0):>6} {block.get('rate', 0.0):>6.1%}"
            )
        return 0

    rows = read_action_plan_records(Path(args.output))
    counts = Counter(str(row.get("send_tier") or "") for row in rows)
    personas = Counter(str(row.get("persona") or "") for row in rows)
    skip_reasons: Counter[str] = Counter()
    for row in rows:
        flags = row.get("risk_flags")
        if isinstance(flags, list):
            for flag in flags:
                if flag:
                    skip_reasons[str(flag)] += 1
    print("Hiring-network ranked plan")
    print(f"records: {len(rows)}")
    print(f"tiers: {dict(counts)}")
    print(f"personas: {dict(personas)}")
    if skip_reasons:
        print(f"risk_flags: {dict(skip_reasons)}")
    for row in rows[:10]:
        print(
            f"- {row.get('send_tier')} score={row.get('rank_score')} "
            f"{row.get('persona')} {row.get('cv_variant')} {row.get('name')}"
        )
    perf = subprocess.call(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "recruiter_performance.py"),
            "--by-persona",
        ]
    )
    return 0 if perf == 0 else perf


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Agentic LinkedIn hiring-network workflow")
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument(
        "--source-action-plan",
        type=Path,
        default=Path("pipeline/recruiter_action_plan.jsonl"),
        help="Scout input from recruiter_orchestrate.py",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=HIRING_NETWORK_ACTION_PLAN_JSONL,
        help="Ranked hiring-network JSONL output",
    )
    ap.add_argument("--browser-channel", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight")

    rank = sub.add_parser("rank", help="Rank an existing scout action plan")
    _ = rank

    daily = sub.add_parser("daily", help="Scout, rank, and optionally auto-send")
    daily.add_argument("--headed", default=True, action=argparse.BooleanOptionalAction)
    daily.add_argument("--dry-run", action="store_true")
    daily.add_argument("--auto-send", action="store_true")
    daily.add_argument("--skip-scout", action="store_true")
    daily.add_argument("--variant", default=None)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument(
        "--headed", default=True, action=argparse.BooleanOptionalAction
    )
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.add_argument("--tier", default="auto_send")
    dispatch.add_argument("--max", type=int, default=None)
    dispatch.add_argument(
        "--only-new",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip profiles already in recruiters.csv (default: on for --full-auto)",
    )

    report = sub.add_parser("report")
    report.add_argument("--persona-stats", action="store_true")

    bridge = sub.add_parser(
        "bridge",
        help="Convert validated CSV to scout JSONL for rank/dispatch",
    )
    bridge.add_argument("--validated-csv", type=Path, default=CANDIDATES_VALIDATED_CSV)
    bridge.add_argument("--action-plan", type=Path, default=ACTION_PLAN_JSONL)
    bridge.add_argument("--approved-only", action="store_true")
    bridge.add_argument("--write-action-plan", action="store_true")
    bridge.add_argument("--dry-run", action="store_true")

    graph = sub.add_parser("graph", help="LangGraph three-agent pipeline")
    graph_sub = graph.add_subparsers(dest="graph_cmd", required=True)
    graph_run = graph_sub.add_parser("run", help="Run graph pipeline stage")
    graph_run.add_argument(
        "--stage",
        default="all",
        choices=("all", "discovery", "validate", "rank", "dispatch"),
    )
    graph_run.add_argument(
        "--dry-run", default=True, action=argparse.BooleanOptionalAction
    )
    graph_run.add_argument("--no-llm", action="store_true")
    graph_run.add_argument(
        "--verbose-llm",
        action="store_true",
        help="Log each Ollama agent call to stderr + pipeline/llm_trace.jsonl",
    )
    graph_run.add_argument(
        "--full-auto",
        action="store_true",
        help="Live send: LLM notes + Playwright Connect (skips CSV review pauses)",
    )
    graph_run.add_argument(
        "--headed", default=True, action=argparse.BooleanOptionalAction
    )
    graph_run.add_argument("--auto-approve-review", action="store_true")
    graph_run.add_argument("--max", type=int, default=None)
    graph_run.add_argument(
        "--backend",
        default="auto",
        choices=("auto", "exa", "firecrawl", "offline"),
    )
    graph_run.add_argument(
        "--discovery-csv", type=Path, default=CANDIDATES_DISCOVERY_CSV
    )
    graph_run.add_argument(
        "--validated-csv", type=Path, default=CANDIDATES_VALIDATED_CSV
    )
    graph_run.add_argument("--action-plan", type=Path, default=ACTION_PLAN_JSONL)
    graph_run.add_argument(
        "--output", type=Path, default=HIRING_NETWORK_ACTION_PLAN_JSONL
    )
    graph_run.add_argument("--no-cache", action="store_true")
    graph_run.add_argument(
        "--no-merge-mcp",
        action="store_true",
        help="Skip merging stale mcp_discovery_batch.jsonl rows into discovery CSV",
    )
    graph_run.add_argument(
        "--only-new",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip profiles already in recruiters.csv (default: on for --full-auto)",
    )
    graph_run.add_argument(
        "--fresh-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Clear action-plan JSONL before run (default: on for --full-auto)",
    )
    graph_run.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip profile enrichment before rank",
    )
    graph_run.add_argument(
        "--enrich-browser",
        action="store_true",
        help="Use Playwright to scrape LinkedIn profiles (requires login)",
    )

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "preflight":
        return cmd_preflight(args)
    if args.cmd == "rank":
        return cmd_rank(args)
    if args.cmd == "daily":
        return cmd_daily(args)
    if args.cmd == "dispatch":
        return cmd_dispatch(args)
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "bridge":
        import yaml
        from recruiter_discovery_bridge import (
            append_scout_records,
            rows_for_bridge,
            validated_to_scout_records,
        )

        rows = read_validated_rows(args.validated_csv)
        bridged = rows_for_bridge(rows, include_review=not args.approved_only)
        cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
        records = validated_to_scout_records(bridged, cfg=cfg)
        print(f"Bridgeable rows: {len(bridged)}")
        for record in records[:10]:
            print(
                f"- {record.get('profile_url')} variant={record.get('variant_slug_best')}"
            )
        if args.write_action_plan and not args.dry_run:
            append_scout_records(records, args.action_plan)
            print(f"Appended {len(records)} scout row(s) to {args.action_plan}")
        return 0
    if args.cmd == "graph":
        from recruiter_graph_workflow import cmd_graph_run

        if args.graph_cmd == "run":
            apply_full_auto_graph_args(args)
            return cmd_graph_run(args)
        raise SystemExit(f"Unknown graph command {args.graph_cmd!r}")
    raise SystemExit(f"Unknown command {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
