"""Deterministic recruiter tier selection and connection-note drafting."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from career_job_search.cvs.matching import load_profiles
from career_job_search.recruiters.matching_core import LT_MARKERS


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


def evidence_phrase_for_outreach(
    *,
    headline: str,
    company: str,
    about: str,
    signals_csv: str,
    persona_evidence: str = "",
) -> str:
    """Prefer headline/company over generic persona labels like 'recruiter'."""
    generic = frozenset(
        {
            "recruiter",
            "hiring",
            "hr",
            "human resources",
            "talent acquisition",
            "hiring and leadership",
        }
    )
    pe = (persona_evidence or "").strip()
    if pe and pe.lower() not in generic and 2 < len(pe) <= 44:
        return pe

    hl = re.sub(r"\s+", " ", (headline or "").strip(" .,:;"))
    if hl and hl.lower() not in generic and len(hl) >= 8:
        return hl[:44]

    co = (company or "").strip()
    if co and hl:
        combo = f"{hl} at {co}"
        return combo[:44]

    phrase = extract_profile_phrase_for_note(headline, about, signals_csv)
    if phrase:
        return phrase[:44]

    if co:
        return co[:44]
    return "your field"


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
    require_clear = bool(
        tier_rule.get(
            "require_clear_winner", matcher.get("require_clear_winner", False)
        )
    )
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
    need_gate = bool(
        tier_rule.get(
            "require_recruiter_gate", matcher.get("require_recruiter_gate", True)
        )
    )
    if meta.get("sales_only_no_hiring"):
        return False, "skipped_sales_only_no_hiring_signal"
    if need_gate and not meta.get("recruiter_gate_ok"):
        return False, "skipped_not_hiring_ecosystem_profile"

    min_score = float(
        tier_rule.get("min_primary_score", matcher.get("min_primary_score", 12))
    )
    min_margin = float(
        tier_rule.get(
            "min_margin_over_second", matcher.get("min_margin_over_second", 4.0)
        )
    )
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

        ok_gate, refusal = meets_tier_scorebar(
            result, matcher=matcher, tier_rule={**matcher, **rule}
        )

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

    FALLBACK_PREVIEW = "Hi {first_name}, I'd like to connect regarding relevant openings in Lithuania — thank you."

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
    if (
        prefer_lt
        and variant_slug == "luxury-retail"
        and isinstance(note_templates.get("luxury-retail-lt"), str)
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
