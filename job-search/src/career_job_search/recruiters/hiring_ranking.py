"""CV matching, ranking, and outreach-note decisions for hiring-network profiles."""

from __future__ import annotations

import re
from typing import Any

from career_job_search.recruiters import matching as rm
from career_job_search.recruiters.hiring_config import (
    _DISCOVERY_PERSONA_PRESERVED,
    _GENERIC_EVIDENCE_TERMS,
    _HIRING_VALIDATION_PERSONAS,
    _VARIANT_CONTEXT_TERMS,
    _automation_cfg,
    _load_full_linkedin_cfg,
    _staffing_only_retail,
    _term_hits,
    industry_hit,
    resolve_persona,
)
from career_job_search.recruiters.hiring_models import (
    CvMatchDecision,
    Decision,
    HistorySignals,
    PersonaDecision,
    ProfileCandidate,
    RankedInvite,
    SendTier,
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
            from career_job_search.recruiters.ollama_embed import blend_cv_score

            score = blend_cv_score(score, candidate.text_blob(), best, full_cfg)
        except Exception:  # noqa: S110
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
        from career_job_search.recruiters.ollama_agents import polish_outreach_note
        from career_job_search.recruiters.ollama_client import agent_enabled

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
    except Exception:  # noqa: S110
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
    _full_cfg: dict[str, Any] | None = None,
) -> float:
    weights = cfg.get("weights") or {}
    history_score = history.score()
    history_boost = 1.0
    full_cfg = _full_cfg if _full_cfg is not None else _load_full_linkedin_cfg()
    if bool((full_cfg.get("automation") or {}).get("use_persona_stats", False)):
        try:
            from career_job_search.recruiters.persona_stats import (
                load_persona_stats,
                persona_boost_factor,
            )

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
