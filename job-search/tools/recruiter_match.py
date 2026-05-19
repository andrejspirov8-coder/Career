"""
Profile text → CV variant scoring for LinkedIn recruiters.

Combines deterministic sector/role signals with matching_lib (job-advert scorer)
as tie-breaker. See linkedin/config.yaml recruiter_matching.*
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from matching_lib import load_profiles, match_job_to_variants

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
    headline_for_title = h or (n.split("\n")[0].strip() if n else "") or "LinkedIn profile"
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
        for k in ("recruiter_gate_terms", "sector_keywords", "sector_beats_cv_min_score")
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


def gate_terms_from_recruiter_cfg(recruiter_cfg: dict[str, Any] | None) -> frozenset[str]:
    """Public helper for logging / orchestrator (full config or recruiter_matching block)."""
    return _gate_terms(_recruiter_matching_section(recruiter_cfg))


def _exclude_terms(yaml_cfg: dict[str, Any] | None) -> frozenset[str]:
    raw = (yaml_cfg or {}).get("outreach_exclude_terms")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).lower().strip() for x in raw if str(x).strip())
    return SALES_ONLY_EXCLUDE_TERMS


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


def is_sales_only_without_hiring_signal(blob_lower: str, yaml_cfg: dict[str, Any] | None) -> bool:
    """Block pure sales/BD profiles that lack recruiter/HR/hiring/leadership hiring cues."""
    gate_terms = _gate_terms(yaml_cfg)
    if profile_has_hiring_gate(blob_lower, gate_terms):
        return False
    exclude = _exclude_terms(yaml_cfg)
    return any(t in blob_lower for t in exclude)


def _score_sectors(blob_lower: str, sector_map: dict[str, list[str]]) -> tuple[dict[str, float], list[str]]:
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
    sector_map = _merged_sector_map(sector_cfg if isinstance(sector_cfg, dict) else None)

    blob = "\n".join(
        x for x in (headline, about, role_text, location, name) if (x or "").strip()
    )
    blob_lower = blob.lower()

    recruiter_gate_ok = profile_has_hiring_gate(blob_lower, gate_terms)
    sales_only_no_hiring = is_sales_only_without_hiring_signal(blob_lower, sector_cfg)

    sector_scores, top_signals = _score_sectors(blob_lower, sector_map)
    sector_slug, sector_top, sector_margin = _pick_sector_variant(sector_scores, sector_cfg)

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
    if sector_slug and sector_top >= float(sector_cfg.get("sector_beats_cv_min_score", 6.0)):
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
        "confidence": cv_conf if chosen == cv_slug else ("clear_winner" if sector_top >= 9 else "tie_review"),
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

    return True, ""


def should_send_connection_request(
    result: dict[str, Any],
    *,
    min_primary_score: float,
    require_clear_winner: bool,
) -> tuple[bool, str]:
    """Legacy wrapper for tests (CV-only thresholds)."""
    rec = result.get("recommendation") or {}
    primary = float(rec.get("primary_score") or 0.0)
    confidence = str(rec.get("confidence") or "")
    if primary < min_primary_score:
        return False, f"skipped_low_score:{primary:.2f}<min:{min_primary_score}"
    if require_clear_winner and confidence != "clear_winner":
        return False, f"skipped_ambiguous:confidence:{confidence}"
    return True, ""


def first_name_from_display(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "there"
    first = n.split()[0].strip(".,;:()[]\"'")
    return first[:40] if first else "there"


def extract_profile_phrase_for_note(
    headline: str,
    about: str,
    signals_csv: str,
    *,
    max_words: int = 14,
) -> str | None:
    """Short authentic snippet from their text, not CV keyword hits."""
    blob = (headline + " " + about).strip()
    if not blob:
        return None
    for token in [s.strip() for s in (signals_csv or "").split(",") if s.strip()]:
        if len(token) < 3:
            continue
        idx = blob.lower().find(token.lower())
        if idx == -1:
            continue
        start = max(0, blob.rfind(".", 0, idx) + 1)
        snippet = blob[start : idx + len(token) + 80].strip()
        words = snippet.split()[:max_words]
        phrase = " ".join(words).strip(".,;: ")
        if 12 <= len(phrase) <= 120:
            return phrase
    words_all = blob.split()
    if len(words_all) >= 5:
        return " ".join(words_all[:8]).strip("., ")
    return None


def variant_anchor_line(variant_slug: str, profiles_path: Path | None = None) -> str:
    """Human-readable headline from variant_profiles.yaml (first target title)."""
    try:
        variants = load_profiles(profiles_path)
    except (FileNotFoundError, ValueError):
        return ""
    block = variants.get(variant_slug) or {}
    titles = block.get("target_titles") or []
    if isinstance(titles, list):
        for t in titles:
            label = str(t).strip()
            if label:
                return label[:100]
    return ""


def _append_suffix_if_room(base: str, suffix: str, max_chars: int) -> str:
    suf = suffix.strip()
    if not suf:
        return base
    chunk = suf if suf.startswith(".") else f" Focus: {suf}"
    if len(base) + len(chunk) + 1 <= max_chars:
        return base + chunk
    return base


def confidence_passes_for_tier(
    confidence: str,
    *,
    matcher: dict[str, Any],
    tier_rule: dict[str, Any],
) -> bool:
    conf = str(confidence or "").strip().lower().replace("-", "_")
    require_clear = bool(tier_rule.get("require_clear_winner", matcher.get("require_clear_winner", False)))
    allow_tie = bool(tier_rule.get("allow_tie_review", False))

    if conf == "clear_winner":
        return True
    if allow_tie and conf == "tie_review":
        return True
    if not require_clear:
        return True
    return False


def meets_tier_scorebar(
    result: dict[str, Any],
    *,
    matcher: dict[str, Any],
    tier_rule: dict[str, Any],
) -> tuple[bool, str]:
    meta = result.get("recruiter_meta") or {}
    rec = result.get("recommendation") or {}
    need_gate = bool(tier_rule.get("require_recruiter_gate", matcher.get("require_recruiter_gate", True)))
    if meta.get("sales_only_no_hiring"):
        return False, "skipped_sales_only_no_hiring_signal"
    if need_gate and not meta.get("recruiter_gate_ok"):
        return False, "skipped_not_hiring_ecosystem_profile"

    min_score = float(tier_rule.get("min_primary_score", matcher.get("min_primary_score", 12)))
    min_margin = float(tier_rule.get("min_margin_over_second", matcher.get("min_margin_over_second", 4.0)))
    primary = float(rec.get("primary_score") or 0.0)
    margin = float(rec.get("margin_over_second") or 0.0)
    confidence = str(rec.get("confidence") or "")

    if primary < min_score:
        return False, f"skipped_low_score:{primary:.2f}<min:{min_score}"
    if margin < min_margin:
        return False, f"skipped_low_margin:{margin:.2f}<min:{min_margin}"
    if not confidence_passes_for_tier(confidence, matcher=matcher, tier_rule=tier_rule):
        return False, f"skipped_ambiguous:confidence:{confidence}"
    return True, ""



def tier_matches_signals(tier_rule: dict[str, Any], company_blob_lower: str) -> bool:


    signals = tier_rule.get("company_signals_any")


    if isinstance(signals, list) and signals:
        blob = company_blob_lower or ""
        if not blob.strip():
            return False
        return any(
            str(signal).strip().lower() and str(signal).lower() in blob
            for signal in signals
            if str(signal).strip()
        )


    return True



def sorted_tier_keys(cfg: dict[str, Any]) -> list[str]:


    block = cfg.get("tiers") or {}


    if not isinstance(block, dict):


        return []




    keys = [k for k in block.keys() if isinstance(k, str) and k.startswith("tier_")]




    def sort_key(token: str) -> tuple[int, str]:




        parts = token.split("_", maxsplit=1)


        suf = parts[1] if len(parts) == 2 else ""


        digits = "".join(ch for ch in suf if ch.isdigit())


        return (int(digits or "999"), suf)




    return sorted(keys, key=sort_key)




def assign_best_tier(


    *,


    result: dict[str, Any],


    cfg: dict[str, Any],


    company_blob_lower: str,


) -> tuple[str, str]:
    matcher = cfg.get("matching") or {}




    for tk in sorted_tier_keys(cfg):


        tblock = cfg.get("tiers") or {}


        rule = (tblock or {}).get(tk) if isinstance(tblock, dict) else {}




        if not isinstance(rule, dict):


            continue




        ok_gate, refusal = meets_tier_scorebar(result, matcher=matcher, tier_rule={**matcher, **rule})


        if not ok_gate:


            continue




        if not tier_matches_signals({**matcher, **rule}, company_blob_lower.lower()):


            continue




        return tk, ""




    return "tier_rest", "no_matching_tier_rule"




def prepare_outreach_note_bundle(




    *,
    match_result: dict[str, Any],


    headline: str,


    about: str,


    location_txt: str,




    display_name: str,


    search_variant_slug: str,


    meta_signals_csv: str,


    note_templates_raw: dict[str, Any],


    matching_cfg: dict[str, Any],




    profiles_path: Path | None = None,




) -> dict[str, str]:
    fname = first_name_from_display(display_name)


    lt_blob = f"{headline} {location_txt} {about}".lower()


    prefer_lt = bool(LT_MARKERS.search(lt_blob))


    recommendation = match_result.get("recommendation") or {}


    best_variant = str(recommendation.get("variant_slug") or search_variant_slug or "")


    template_literal = pick_template_for_profile(
        best_variant, note_templates=note_templates_raw, prefer_lt=prefer_lt


    )




    if not template_literal:


        bk = note_templates_raw.get(search_variant_slug)


        if isinstance(bk, str) and bk.strip():


            template_literal = bk.strip()




    phrase = extract_profile_phrase_for_note(headline, about, meta_signals_csv)


    anchor = variant_anchor_line(best_variant, profiles_path)


    note_max_chars = int(matching_cfg.get("note_max_chars", 280))


    FALLBACK_PREVIEW = (
        "Hi {first_name}, I'd like to connect regarding relevant openings in Lithuania — thank you."
    )


    preview_tmpl = template_literal or FALLBACK_PREVIEW




    drafted_preview = build_personalized_connection_note(


        preview_tmpl,




        first_name=fname,




        profile_phrase=phrase,




        max_chars=note_max_chars,




    )




    base_live_template = template_literal




    drafted_live_raw = ""




    if base_live_template:


        drafted_live_raw = build_personalized_connection_note(


            base_live_template,




            first_name=fname,




            profile_phrase=phrase,




            max_chars=note_max_chars,




        )





    appended = drafted_live_raw


    if appended and anchor:


        appended = _append_suffix_if_room(appended, anchor, note_max_chars)




    if bool(matching_cfg.get("append_top_keyword_hit_to_note_if_fits_chars", False)):
        kw = top_keyword_hit(match_result)
        base_for_kw = (appended or "").strip()
        if kw and base_for_kw:
            addon = f" Context: strong fit around {kw}."
            if len(base_for_kw) + len(addon) <= note_max_chars:
                appended = base_for_kw + addon
            elif note_max_chars > 25:
                room = note_max_chars - len(addon) - 2
                if room > 20:
                    appended = base_for_kw[:room].rstrip() + addon

    drafted_live_final = appended or drafted_preview




    preview_snip_exp = ""




    if base_live_template:




        preview_snip_exp = drafted_preview[:220]






    return {




        "template_used": template_literal or "",




        "note_preview_trim": drafted_live_final[:220],




        "note_live_full": drafted_live_final,





        "preview_with_fallback": drafted_preview,




        "preview_excerpt_logged": preview_snip_exp,





    }







def prepare_outreach_note(**kwargs: Any) -> dict[str, str]:
    """Single matcher entry alias; delegates to prepare_outreach_note_bundle."""
    return prepare_outreach_note_bundle(**kwargs)


def pick_template_for_profile(
    variant_slug: str,
    *,
    note_templates: dict[str, str],
    prefer_lt: bool,
) -> str:
    if prefer_lt and variant_slug == "luxury-retail" and isinstance(
        note_templates.get("luxury-retail-lt"), str
    ):
        return str(note_templates["luxury-retail-lt"])
    t = note_templates.get(variant_slug)
    return str(t) if isinstance(t, str) and t.strip() else ""


def build_personalized_connection_note(
    template: str,
    *,
    first_name: str,
    profile_phrase: str | None,
    max_chars: int,
) -> str:
    raw = template.format(first_name=first_name).strip()
    if profile_phrase and len(raw) + len(profile_phrase) + 8 <= max_chars:
        raw = raw + f" ({profile_phrase[:90]})"
    if len(raw) <= max_chars:
        return raw
    return raw[: max(0, max_chars - 3)].rstrip() + "..."


def build_connection_note(
    template: str,
    *,
    first_name: str,
    top_keyword: str | None,
    append_keyword: bool,
    max_chars: int,
) -> str:
    """Backward-compatible wrapper."""
    raw = template.format(first_name=first_name).strip()
    if append_keyword and top_keyword:
        addon = f" Context: strong fit around {top_keyword}."
        if len(raw + addon) <= max_chars:
            raw = raw + addon
    if len(raw) <= max_chars:
        return raw
    return raw[: max(0, max_chars - 3)].rstrip() + "..."


def top_keyword_hit(result: dict[str, Any]) -> str | None:
    ranked = result.get("variants_ranked") or []
    if not ranked:
        return None
    top = ranked[0]
    hits = top.get("keyword_hits") or []
    if not hits:
        return None
    return hits[0] if isinstance(hits[0], str) else None
