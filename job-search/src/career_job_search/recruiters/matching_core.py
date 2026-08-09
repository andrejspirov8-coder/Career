"""
Profile text → CV variant scoring for LinkedIn recruiters.

Combines deterministic sector/role signals with matching_lib (job-advert scorer)
as tie-breaker. See linkedin/config.yaml recruiter_matching.*
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from career_job_search.cvs.matching import load_profiles, match_job_to_variants

LT_MARKERS = re.compile(
    r"\b(lietuva|lietuvos|vilnius|vilniaus|personalo|ieškau|darbuotojų|pardavim)\w*",
    re.I,
)

# Headline/about must match at least one term when require_recruiter_gate is true.
# Covers recruiters plus hiring managers, HR, and retail/ops leadership with hiring signal.
DEFAULT_GATE_TERMS = frozenset(
    {
        "recruiter",
        "talent acquisition",
        "talent partner",
        "headhunter",
        "executive search",
        "staffing",
        "personalo",
        "personalo vadov",
        "personalo specialist",
        "personalo skyrius",
        "įdarbinim",
        "darbuotojų",
        "talent",
        "hiring manager",
        "head of people",
        "people & culture",
        "people and culture",
        "people operations",
        "human resources",
        "hr manager",
        "hr business partner",
        "hrbp",
        "hr generalist",
        "chief people officer",
        "head of hr",
        "head of human resources",
        "people partner",
        "recruitment manager",
        "in-house recruiter",
        "corporate recruiter",
        "area manager",
        "regional manager",
        "district manager",
        "cluster manager",
        "store director",
        "retail director",
        "operations director",
        "director of operations",
        "director of retail",
        "director of stores",
        "general manager",
        "general manager retail",
        "country manager retail",
        "learning and development",
        "l&d manager",
        "employee experience",
        "workforce planning",
        "vadovas",
        "direktorius",
        "personalo vadovė",
        "personalo verslo partner",
        "regiono vadov",
        "parduotuvės direktor",
        "mažmeninės prekybos direktor",
        "įdarbinimo vadov",
    }
)

# Pure sales / IC outreach targets — skip unless a hiring gate term also matches.
SALES_ONLY_EXCLUDE_TERMS = frozenset(
    {
        "b2b sales",
        "account executive",
        "business development representative",
        "sales development representative",
        "sales representative",
        "inside sales",
        "field sales",
        "key account manager",
        "commercial manager",  # often sales-led; gate terms override when HR/hiring present
    }
)

# Base sector keyword → variant_slug (weights applied per hit)
DEFAULT_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "luxury-retail": [
        "luxury",
        "premium retail",
        "premium fashion",
        "boutique",
        "fashion",
        "clienteling",
        "harrods",
        "visual merchandising",
        "store director",
        "retail director",
        "head of retail",
        "area manager",
        "regional manager",
        "sales associate",
        "client advisor",
        "prabangos",
        "prabangi",
    ],
    "luxury-retail-lt": [
        "prabangos",
        "prabangi",
        "pardavim",
        "parduotuv",
        "vilniaus retail",
        "mažmen",
    ],
    "operations-management": [
        "operations",
        "multi-site",
        "multi site",
        "hospitality",
        "service excellence",
        "area manager",
        "regional manager",
        "district manager",
        "operations director",
        "general manager",
        "retail operations",
        "store operations",
        "team leadership",
    ],
    "it-business": [
        "it support",
        "technical support",
        "helpdesk",
        "help desk",
        "business analyst",
        "systems analyst",
        "sap",
        "infrastructure",
    ],
}


def normalize_profile_fields(fields: dict[str, str]) -> dict[str, str]:
    return {k: (v or "").strip() for k, v in fields.items()}


def build_parsed_job_from_profile(
    *,
    headline: str,
    name: str,
    url: str,
    company: str,
    about: str,
    role_text: str,
    location: str,
) -> dict[str, Any]:
    h = headline.strip()
    n = name.strip()
    headline_for_title = (
        h or (n.split("\n")[0].strip() if n else "") or "LinkedIn profile"
    )
    body_parts = [about, role_text, location]
    body = "\n".join(p for p in body_parts if (p or "").strip()).strip()
    title_boost = " ".join(x for x in (h, n) if x).lower()
    return {
        "title": headline_for_title,
        "company": company.strip(),
        "url": url.strip(),
        "source": "linkedin_profile",
        "body": body,
        "title_boost_region": title_boost,
        "profile_name": n,
        "linkedin_url": url.strip(),
    }


def match_profile(
    *,
    headline: str,
    name: str,
    profile_url: str,
    company: str = "",
    about: str = "",
    role_text: str = "",
    location: str = "",
    profiles_path: Path | None = None,
) -> dict[str, Any]:
    variants = load_profiles(profiles_path)
    parsed = build_parsed_job_from_profile(
        headline=headline,
        name=name,
        url=profile_url,
        company=company,
        about=about,
        role_text=role_text,
        location=location,
    )
    if not parsed["body"].strip() and not parsed["title_boost_region"]:
        parsed["body"] = "(empty profile scrape)"
    return match_job_to_variants(parsed, variants)


def _recruiter_matching_section(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the `recruiter_matching:` block whether the caller passes full config or only that block."""
    if not cfg:
        return {}
    inner = cfg.get("recruiter_matching")
    if isinstance(inner, dict):
        return inner
    if any(
        k in cfg
        for k in (
            "recruiter_gate_terms",
            "sector_keywords",
            "sector_beats_cv_min_score",
        )
    ):
        return cfg
    return {}


def _merged_sector_map(yaml_cfg: dict[str, Any] | None) -> dict[str, list[str]]:
    base = {k: list(v) for k, v in DEFAULT_SECTOR_KEYWORDS.items()}
    if not yaml_cfg:
        return base
    override = yaml_cfg.get("sector_keywords") or {}
    if isinstance(override, dict):
        for slug, phrases in override.items():
            if isinstance(phrases, list) and slug in base:
                base[slug] = [str(x) for x in phrases if str(x).strip()]
    return base


def _gate_terms(yaml_cfg: dict[str, Any] | None) -> frozenset[str]:
    raw = (yaml_cfg or {}).get("recruiter_gate_terms")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).lower().strip() for x in raw if str(x).strip())
    return DEFAULT_GATE_TERMS


def gate_terms_from_recruiter_cfg(
    recruiter_cfg: dict[str, Any] | None,
) -> frozenset[str]:
    """Public helper for logging / orchestrator (full config or recruiter_matching block)."""
    return _gate_terms(_recruiter_matching_section(recruiter_cfg))


def _exclude_terms(yaml_cfg: dict[str, Any] | None) -> frozenset[str]:
    raw = (yaml_cfg or {}).get("outreach_exclude_terms")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).lower().strip() for x in raw if str(x).strip())
    return SALES_ONLY_EXCLUDE_TERMS


def _term_in_blob(blob_lower: str, term: str) -> bool:
    """Match phrases with word boundaries for single tokens and raw substring for phrases."""
    t = term.lower().strip()
    if not t:
        return False
    if " " in t or "-" in t:
        return t in blob_lower
    return bool(re.search(rf"\b{re.escape(t)}\b", blob_lower))


def _outreach_exclude_terms(full_cfg: dict[str, Any] | None) -> frozenset[str]:
    """Sector outreach excludes from recruiter_matching or hiring_network."""
    if not full_cfg:
        return frozenset()
    rm = _recruiter_matching_section(full_cfg)
    raw = rm.get("outreach_exclude_terms")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).lower().strip() for x in raw if str(x).strip())
    hn = full_cfg.get("hiring_network") or {}
    raw2 = hn.get("outreach_exclude_terms") if isinstance(hn, dict) else None
    if isinstance(raw2, list) and raw2:
        return frozenset(str(x).lower().strip() for x in raw2 if str(x).strip())
    return frozenset()


def _track_aligned_terms(full_cfg: dict[str, Any] | None) -> list[str]:
    if not full_cfg:
        return []
    rm = _recruiter_matching_section(full_cfg)
    raw = rm.get("track_aligned_company_terms")
    if isinstance(raw, list) and raw:
        return [str(x).lower().strip() for x in raw if str(x).strip()]
    hn = full_cfg.get("hiring_network") or {}
    raw2 = hn.get("track_aligned_company_terms") if isinstance(hn, dict) else None
    if isinstance(raw2, list) and raw2:
        return [str(x).lower().strip() for x in raw2 if str(x).strip()]
    return []


def profile_has_outreach_exclude(
    blob_lower: str, full_cfg: dict[str, Any] | None
) -> bool:
    excludes = _outreach_exclude_terms(full_cfg)
    return bool(excludes) and any(_term_in_blob(blob_lower, t) for t in excludes)


def profile_has_track_industry(
    blob_lower: str,
    *,
    variant_slug: str,
    full_cfg: dict[str, Any] | None,
) -> bool:
    """True when profile shows a track-aligned industry/sector signal."""
    if any(_term_in_blob(blob_lower, t) for t in _track_aligned_terms(full_cfg)):
        return True
    sector_map = _merged_sector_map(_recruiter_matching_section(full_cfg))
    phrases = sector_map.get(variant_slug) or []
    return any(_term_in_blob(blob_lower, p) for p in phrases if len(p) >= 3)


def profile_negative_hits(
    blob_lower: str,
    variant_slug: str,
    profiles_path: Path | None = None,
) -> list[str]:
    """Negative keywords from variant_profiles.yaml that appear in profile text."""
    try:
        variants = load_profiles(profiles_path)
    except (FileNotFoundError, ValueError):
        return []
    block = variants.get(variant_slug) or {}
    negs = block.get("negative_keywords") or []
    hits: list[str] = []
    for neg in negs:
        n = str(neg).lower().strip()
        if len(n) < 3:
            continue
        if _term_in_blob(blob_lower, n):
            hits.append(n)
    return hits


def passes_track_relevance_gate(
    result: dict[str, Any],
    *,
    full_cfg: dict[str, Any] | None,
    matcher: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Optional stricter gate: industry + CV floor + profile negatives."""
    candidate = matcher or (full_cfg or {}).get("matching") or {}
    matcher = candidate if isinstance(candidate, dict) else {}
    if not bool(matcher.get("require_sector_and_cv_agreement", False)):
        return True, ""

    meta = result.get("recruiter_meta") or {}
    rec = result.get("recommendation") or {}
    variant = str(rec.get("variant_slug") or "")
    blob = str(meta.get("profile_blob_excerpt") or "").lower()
    if not blob:
        return True, ""

    if profile_has_outreach_exclude(blob, full_cfg):
        return False, "skipped_outreach_exclude_term"

    cv_primary = float(rec.get("cv_primary_score") or 0.0)
    cv_mins = matcher.get("cv_min_scores") or {}
    min_cv = float(cv_mins.get(variant, 8.0)) if isinstance(cv_mins, dict) else 8.0
    if cv_primary < min_cv:
        return False, f"skipped_low_cv_fit:{cv_primary:.2f}<min:{min_cv}"

    neg_hits = profile_negative_hits(blob, variant)
    sector_top = float(meta.get("sector_top_score") or 0.0)
    if neg_hits and sector_top < 6.0:
        return False, f"skipped_profile_negative:{','.join(neg_hits[:3])}"

    if not profile_has_track_industry(blob, variant_slug=variant, full_cfg=full_cfg):
        company_priority = []
        if full_cfg:
            hn = full_cfg.get("hiring_network") or {}
            company_priority = hn.get("company_priority_terms") or []
        if not any(str(t).lower() in blob for t in company_priority if str(t).strip()):
            return False, "skipped_no_track_industry_signal"

    return True, ""


def _gate_term_matches(blob_lower: str, term: str) -> bool:
    """Phrase match; multi-word terms avoid accidental substring hits (e.g. team manager ≠ general manager)."""
    t = term.lower().strip()
    if not t:
        return False
    if " " in t or "-" in t:
        return t in blob_lower
    return bool(re.search(rf"\b{re.escape(t)}\b", blob_lower))


def matched_hiring_gate_terms(blob_lower: str, gate_terms: frozenset[str]) -> list[str]:
    """Terms that satisfied the hiring-ecosystem gate (for logging)."""
    found: list[str] = []
    for term in sorted(gate_terms, key=len, reverse=True):
        if _gate_term_matches(blob_lower, term) and term not in found:
            found.append(term)
    if re.search(r"\bhr\b", blob_lower) and "hr" not in found:
        found.append("hr")
    return found[:6]


def profile_has_hiring_gate(blob_lower: str, gate_terms: frozenset[str]) -> bool:
    return bool(matched_hiring_gate_terms(blob_lower, gate_terms))


def is_sales_only_without_hiring_signal(
    blob_lower: str, yaml_cfg: dict[str, Any] | None
) -> bool:
    """Block pure sales/BD profiles that lack recruiter/HR/hiring/leadership hiring cues."""
    gate_terms = _gate_terms(yaml_cfg)
    if profile_has_hiring_gate(blob_lower, gate_terms):
        return False
    exclude = _exclude_terms(yaml_cfg)
    return any(t in blob_lower for t in exclude)


def _score_sectors(
    blob_lower: str, sector_map: dict[str, list[str]]
) -> tuple[dict[str, float], list[str]]:
    scores: dict[str, float] = {slug: 0.0 for slug in sector_map}
    signals: list[str] = []
    for slug, phrases in sector_map.items():
        for phrase in phrases:
            pl = phrase.lower().strip()
            if len(pl) < 2:
                continue
            if pl in blob_lower:
                scores[slug] += 3.0
                if phrase not in signals:
                    signals.append(phrase[:48])
    return scores, signals[:12]


def _pick_sector_variant(
    scores: dict[str, float],
    sector_cfg: dict[str, Any] | None,
) -> tuple[str, float, float]:
    """Return (slug, top_score, margin_to_second)."""
    min_beats = float((sector_cfg or {}).get("sector_beats_cv_min_score", 6.0))
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    if not ranked:
        return "", 0.0, 0.0
    top_slug, top_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = top_s - second_s
    if top_s < min_beats:
        return "", top_s, margin
    return top_slug, top_s, margin


def match_recruiter_profile(
    *,
    headline: str,
    name: str,
    profile_url: str,
    company: str = "",
    about: str = "",
    role_text: str = "",
    location: str = "",
    profiles_path: Path | None = None,
    recruiter_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Sector + CV hybrid. Sets recommendation from sector when strong enough, else CV matcher.
    Adds: top_signals, recruiter_gate_ok, sector_slug, sector_score, cv_recommendation (copy).
    """
    sector_cfg = _recruiter_matching_section(recruiter_cfg)
    gate_terms = _gate_terms(sector_cfg if isinstance(sector_cfg, dict) else None)
    sector_map = _merged_sector_map(
        sector_cfg if isinstance(sector_cfg, dict) else None
    )

    blob = "\n".join(
        x
        for x in (headline, company, about, role_text, location, name)
        if (x or "").strip()
    )
    blob_lower = blob.lower()

    recruiter_gate_ok = profile_has_hiring_gate(blob_lower, gate_terms)
    sales_only_no_hiring = is_sales_only_without_hiring_signal(blob_lower, sector_cfg)

    sector_scores, top_signals = _score_sectors(blob_lower, sector_map)
    sector_slug, sector_top, sector_margin = _pick_sector_variant(
        sector_scores, sector_cfg
    )

    cv_result = match_profile(
        headline=headline,
        name=name,
        profile_url=profile_url,
        company=company,
        about=about,
        role_text=role_text,
        location=location,
        profiles_path=profiles_path,
    )

    cv_rec = cv_result.get("recommendation") or {}
    cv_slug = str(cv_rec.get("variant_slug") or "")
    cv_primary = float(cv_rec.get("primary_score") or 0.0)
    cv_conf = str(cv_rec.get("confidence") or "")
    cv_margin = float(cv_rec.get("margin_over_second") or 0.0)

    # Resolve final variant: strong sector beats CV; LT language nudges luxury → luxury-retail-lt
    if sector_slug and sector_top >= float(
        sector_cfg.get("sector_beats_cv_min_score", 6.0)
    ):
        chosen = sector_slug
        if chosen == "luxury-retail" and LT_MARKERS.search(blob):
            if "luxury-retail-lt" in sector_scores:
                chosen = "luxury-retail-lt"
    else:
        chosen = cv_slug

    unified = max(sector_top * 2.2 + 0.4 * cv_primary, cv_primary)

    margin_use = max(sector_margin, cv_margin)

    runner = cv_result.get("runner_up") or {}
    rec_out = {
        "variant_slug": chosen,
        "confidence": cv_conf
        if chosen == cv_slug
        else ("clear_winner" if sector_top >= 9 else "tie_review"),
        "primary_score": round(unified, 4),
        "tie_break_score": float(cv_rec.get("tie_break_score") or 0),
        "margin_over_second": margin_use,
        "cv_primary_score": cv_primary,
        "sector_primary_score": sector_top,
        "runner_up_slug": str(runner.get("variant_slug") or ""),
        "runner_up_score": float(runner.get("primary_score") or 0.0),
    }

    return {
        **cv_result,
        "recommendation": rec_out,
        "runner_up": runner,
        "recruiter_meta": {
            "top_signals": ", ".join(top_signals),
            "recruiter_gate_ok": recruiter_gate_ok,
            "sales_only_no_hiring": sales_only_no_hiring,
            "sector_slug": sector_slug,
            "sector_top_score": sector_top,
            "sector_margin": sector_margin,
            "cv_chosen_slug": cv_slug,
            "profile_blob_excerpt": blob[:600],
        },
    }


def should_send_recruiter_connection(
    result: dict[str, Any],
    *,
    min_primary_score: float,
    min_margin_over_second: float,
    require_clear_winner: bool,
    require_recruiter_gate: bool,
    full_cfg: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    meta = result.get("recruiter_meta") or {}
    if meta.get("sales_only_no_hiring"):
        return False, "skipped_sales_only_no_hiring_signal"
    if require_recruiter_gate and not meta.get("recruiter_gate_ok"):
        return False, "skipped_not_hiring_ecosystem_profile"

    rec = result.get("recommendation") or {}
    primary = float(rec.get("primary_score") or 0.0)
    margin = float(rec.get("margin_over_second") or 0.0)
    confidence = str(rec.get("confidence") or "")

    if primary < min_primary_score:
        return False, f"skipped_low_score:{primary:.2f}<min:{min_primary_score}"

    if margin < min_margin_over_second:
        return False, f"skipped_low_margin:{margin:.2f}<min:{min_margin_over_second}"

    if require_clear_winner and confidence != "clear_winner":
        return False, f"skipped_ambiguous:confidence:{confidence}"

    matcher = (full_cfg or {}).get("matching") or {}
    ok_track, track_refusal = passes_track_relevance_gate(
        result, full_cfg=full_cfg, matcher=matcher
    )
    if not ok_track:
        return False, track_refusal

    return True, ""
