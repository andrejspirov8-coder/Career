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
import math
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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import linkedin_selectors as lis
import recruiter_match as rm
from matching_lib import PROFILES_PATH, load_profiles
from recruiter_linkedin_paths import (
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
    "hiring_manager",
    "retail_area_leader",
    "store_director",
    "operations_leader",
    "it_business_leader",
    "low_relevance",
]

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
        return max(0.0, min(100.0, 100.0 * (0.4 * accept + 0.4 * reply + 0.2 * interview)))


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
            "hiring_manager": 88,
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
            "hiring_manager": [
                "hiring manager",
                "head of department",
                "team lead",
                "department manager",
                "country manager",
                "director",
                "vadovas",
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


def classify_persona(candidate: ProfileCandidate, cfg: dict[str, Any]) -> PersonaDecision:
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

    priority = [
        "retail_area_leader",
        "store_director",
        "operations_leader",
        "it_business_leader",
        "recruiter_hr",
        "hiring_manager",
    ]
    picked = ""
    for persona in priority:
        if persona in scores:
            picked = persona
            break

    if not picked:
        return PersonaDecision(
            persona="low_relevance",
            hiring_authority_score=0,
            confidence=0.2,
            evidence=[],
            risk_flags=["no_hiring_network_signal"],
        )

    hits = scores[picked][:6]
    base_score = float((cfg.get("persona_weights") or {}).get(picked, 70))
    extra = min(8.0, max(0, len(hits) - 1) * 2.0)
    confidence = min(0.98, 0.68 + 0.08 * len(hits))
    return PersonaDecision(
        persona=picked,  # type: ignore[arg-type]
        hiring_authority_score=min(100.0, base_score + extra),
        confidence=confidence,
        evidence=hits,
        risk_flags=[],
    )


def candidate_from_scout_record(record: dict[str, Any]) -> ProfileCandidate:
    text = "\n".join(
        str(record.get(k) or "")
        for k in (
            "scraped_about_excerpt",
            "about",
            "role_text",
            "top_signals",
            "note_preview_trim",
        )
        if str(record.get(k) or "").strip()
    )
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
    )


def match_candidate_to_cv(candidate: ProfileCandidate, cfg: dict[str, Any]) -> CvMatchDecision:
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
        best = str(rec.get("variant_slug") or candidate.search_variant_slug or "luxury-retail")
        raw_score = float(rec.get("primary_score") or 0.0)
        score = max(0.0, min(100.0, raw_score * 5.0))
        margin = float(rec.get("margin_over_second") or 0.0)
        conf_raw = str(rec.get("confidence") or "")
        confidence = 0.86 if conf_raw == "clear_winner" else 0.64
        if margin >= 4:
            confidence = min(0.96, confidence + 0.08)
        evidence = [x.strip() for x in str(meta.get("top_signals") or "").split(",") if x.strip()]
        if not evidence and ranked:
            hits = ranked[0].get("keyword_hits") or []
            evidence = [str(x) for x in hits[:5]]
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
    hits = _term_hits(blob, [str(x) for x in cfg.get("company_priority_terms", [])])
    return min(100.0, len(hits) * 18.0)


def geography_score(candidate: ProfileCandidate, cfg: dict[str, Any]) -> float:
    blob = candidate.text_blob().lower()
    hits = _term_hits(blob, [str(x) for x in cfg.get("geography_terms", [])])
    if not hits:
        return 35.0
    if any(x in hits for x in ("vilnius", "lithuania", "lietuva")):
        return 100.0
    return min(90.0, 55.0 + 15.0 * len(hits))


def personalization_score(candidate: ProfileCandidate, persona: PersonaDecision, cv: CvMatchDecision) -> float:
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


def compact_evidence(persona: PersonaDecision, cv: CvMatchDecision) -> str:
    for source in (persona.evidence, cv.evidence):
        for item in source:
            clean = re.sub(r"\s+", " ", item).strip(" .,:;")
            if 2 <= len(clean) <= 44:
                return clean
    return "hiring and leadership"


def write_personalized_note(
    candidate: ProfileCandidate,
    persona: PersonaDecision,
    cv: CvMatchDecision,
    cfg: dict[str, Any],
) -> tuple[str, str]:
    templates = cfg.get("persona_note_templates") or {}
    template = str(templates.get(persona.persona) or templates.get("hiring_manager") or "")
    if not template:
        template = (
            "Hi {first_name}, I am exploring {cv_focus} roles around {geo}. "
            "Would value connecting given your work in {evidence}."
        )
    note = template.format(
        first_name=first_name(candidate.name),
        cv_focus=cv_focus_label(cv.best_cv_variant),
        geo=geo_label(candidate),
        evidence=compact_evidence(persona, cv),
    )
    note = re.sub(r"\s+", " ", note).strip()
    if len(note) > 280:
        note = note[:277].rstrip(" ,.;:") + "..."
    reason = f"{persona.persona}:{compact_evidence(persona, cv)}:{cv.best_cv_variant}"
    return note, reason


def rank_candidate(
    candidate: ProfileCandidate,
    persona: PersonaDecision,
    cv: CvMatchDecision,
    cfg: dict[str, Any],
    history: HistorySignals,
) -> float:
    weights = cfg.get("weights") or {}
    components = {
        "cv_fit": cv.score,
        "hiring_authority": persona.hiring_authority_score,
        "company_sector": company_sector_score(candidate, cfg),
        "geography": geography_score(candidate, cfg),
        "personalization": personalization_score(candidate, persona, cv),
        "history": history.score(),
    }
    total_weight = sum(float(weights.get(k, 0.0)) for k in components) or 1.0
    score = sum(float(weights.get(k, 0.0)) * v for k, v in components.items()) / total_weight
    return round(max(0.0, min(100.0, score)), 4)


def build_ranked_invite(
    candidate: ProfileCandidate,
    *,
    cfg: dict[str, Any],
    history: HistorySignals,
    already_contacted: bool,
    pending_visible: bool,
) -> RankedInvite:
    persona = classify_persona(candidate, cfg)
    cv = match_candidate_to_cv(candidate, cfg)
    rank_score = rank_candidate(candidate, persona, cv, cfg, history)
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

    if risk_flags:
        send_tier: SendTier = "skip"
        decision: Decision = "skip"
    elif rank_score >= float(cfg.get("auto_send_threshold", 76.0)):
        send_tier = "auto_send"
        decision = "approved"
    elif rank_score >= float(cfg.get("queue_review_threshold", 58.0)):
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


def load_history_by_variant(csv_path: Path = RECRUITERS_CSV) -> dict[str, HistorySignals]:
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
        )
        invites.append(invite)

    invites.sort(key=lambda x: (-x.rank_score, x.candidate.name.lower(), x.candidate.profile_url))
    return invites


def classify_screen_state_from_text(text: str) -> ScreenState:
    blob = text.lower()
    if "captcha" in blob or "prove you're human" in blob or "prove youre human" in blob:
        return "captcha"
    if "checkpoint" in blob or "security verification" in blob or "verify your identity" in blob:
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


def build_langgraph_workflow() -> Any:
    """Build the LangGraph shell when the dependency is installed."""
    try:
        from langgraph.graph import END, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError("LangGraph is not installed. Run: pip install -r requirements.txt") from exc

    def identity_node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    graph = StateGraph(dict)
    for node_name in (
        "preflight",
        "scout",
        "profile_classifier",
        "cv_matcher",
        "ranker",
        "note_writer",
        "safety_governor",
        "dispatcher",
        "followup_learner",
    ):
        graph.add_node(node_name, identity_node)
    graph.set_entry_point("preflight")
    graph.add_edge("preflight", "scout")
    graph.add_edge("scout", "profile_classifier")
    graph.add_edge("profile_classifier", "cv_matcher")
    graph.add_edge("cv_matcher", "ranker")
    graph.add_edge("ranker", "note_writer")
    graph.add_edge("note_writer", "safety_governor")
    graph.add_edge("safety_governor", "dispatcher")
    graph.add_edge("dispatcher", "followup_learner")
    graph.add_edge("followup_learner", END)
    return graph.compile()


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
                raw = yaml.safe_load(DEFAULT_LINKEDIN_CONFIG.read_text(encoding="utf-8")) or {}
                limits = raw.get("limits") or {}
            print(f"Effective invite cap: {bot.effective_daily_invite_cap(limits)}")
        except Exception as exc:
            print(f"Effective invite cap: unavailable ({exc})")
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


def _approved_invites_from_plan(path: Path, *, tier: str, max_profiles: int | None) -> list[dict[str, Any]]:
    rows = read_action_plan_records(path)
    approved: list[dict[str, Any]] = []
    for row in rows:
        if row.get("decision") != "approved":
            continue
        if tier and tier != "all" and row.get("send_tier") != tier:
            continue
        approved.append(row)
        if max_profiles is not None and len(approved) >= max_profiles:
            break
    return approved


def cmd_dispatch(args: argparse.Namespace) -> int:
    if bot is None:
        raise SystemExit("Playwright dispatcher unavailable: install requirements.txt first.")
    approved = _approved_invites_from_plan(Path(args.output), tier=args.tier, max_profiles=args.max)
    if not approved:
        raise SystemExit("No approved invites to dispatch.")
    raw_cfg = bot.load_config(Path(args.config))
    queued = [
        (
            lis.canonical_profile_url(row.get("profile_url") or ""),
            str(row.get("cv_variant") or ""),
        )
        for row in approved
    ]
    queued = [(u, v) for u, v in queued if u and v]
    planned = {
        lis.canonical_profile_url(row.get("profile_url") or ""): {
            "note": row.get("note") or "",
            "persona": row.get("persona") or "",
            "rank_score": row.get("rank_score") or "",
            "profile_confidence": row.get("persona_confidence") or "",
            "safety_decision": row.get("decision") or "",
            "note_reason": row.get("note_reason") or "",
        }
        for row in approved
    }
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
    rows = read_action_plan_records(Path(args.output))
    counts = Counter(str(row.get("send_tier") or "") for row in rows)
    personas = Counter(str(row.get("persona") or "") for row in rows)
    print("Hiring-network ranked plan")
    print(f"records: {len(rows)}")
    print(f"tiers: {dict(counts)}")
    print(f"personas: {dict(personas)}")
    for row in rows[:10]:
        print(
            f"- {row.get('send_tier')} score={row.get('rank_score')} "
            f"{row.get('persona')} {row.get('cv_variant')} {row.get('name')}"
        )
    return 0


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
    dispatch.add_argument("--headed", default=True, action=argparse.BooleanOptionalAction)
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.add_argument("--tier", default="auto_send")
    dispatch.add_argument("--max", type=int, default=None)

    sub.add_parser("report")
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
    raise SystemExit(f"Unknown command {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
