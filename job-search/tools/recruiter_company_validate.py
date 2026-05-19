#!/usr/bin/env python3
"""Second-pass company relevance validation for discovery CSV rows."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import hiring_network_workflow as hn
from recruiter_discovery_csv import (
    discovery_to_validated,
    read_discovery_rows,
    sort_by_rank_score,
    today_iso,
    write_validated_rows,
)
from recruiter_linkedin_paths import (
    CANDIDATES_DISCOVERY_CSV,
    CANDIDATES_VALIDATED_CSV,
    DEFAULT_LINKEDIN_CONFIG,
)
from recruiter_web_research import company_site_hits, web_search

try:
    from recruiter_ollama_agents import analyze_company
    from recruiter_ollama_client import agent_enabled
except ImportError:
    analyze_company = None  # type: ignore[misc, assignment]
    agent_enabled = lambda *a, **k: False  # type: ignore[misc, assignment]


def load_full_cfg(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def company_validation_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("company_validation") or {}


def _profile_in_lithuania(location: str) -> bool:
    return bool(
        re.search(
            r"\b(vilnius|vilniaus|kaunas|klaip[eė]da|lithuania|lietuva)\b",
            location or "",
            re.I,
        )
    )


def _profile_abroad(location: str) -> bool:
    return bool(
        re.search(
            r"\((US|FI|ES|LV|DE|GB|UK)\)|United States|Boston|New York|Helsinki|Spain|Riga, Latvia",
            location or "",
            re.I,
        )
    )


# Personas that work across sectors and should not be filtered out by strict
# sector alignment alone (HR/talent acquisition often staff for any industry).
_CROSS_SECTOR_PERSONAS = frozenset(
    {
        "recruiter_hr",
        "talent_acquisition",
        "executive_search",
        "hiring_manager",
    }
)


def _persona_validation_boost(
    *,
    persona: str,
    cv_block: dict[str, Any],
    hard_reject_flags: list[str],
) -> tuple[float, str]:
    """Add a configurable bump for cross-sector personas with no hard flags."""
    if not persona or persona not in _CROSS_SECTOR_PERSONAS:
        return 0.0, ""
    if hard_reject_flags:
        return 0.0, ""
    boost = float(cv_block.get("persona_cross_sector_boost") or 0.0)
    if boost <= 0:
        return 0.0, ""
    label = persona.replace("_", " ")
    return boost, f"{label} boost (+{boost:.0f})"


def score_company_from_text(
    company: str,
    blob: str,
    *,
    hn_cfg: dict[str, Any],
    cv_cfg: dict[str, Any],
    profile_location: str = "",
    persona: str = "",
) -> tuple[float, list[str], str]:
    blob_lower = blob.lower()
    flags: list[str] = []
    exclude_terms = [
        str(x).lower()
        for x in (hn_cfg.get("outreach_exclude_terms") or [])
        if str(x).strip()
    ]
    for term in exclude_terms:
        if term and term in blob_lower:
            flags.append("outreach_exclude_term")
            break

    candidate = hn.ProfileCandidate(
        profile_url="https://www.linkedin.com/in/company-check/",
        name="Company Check",
        headline=f"{company} hiring",
        company=company,
        scraped_text=blob[:800],
        location=profile_location or "Lithuania",
    )
    sector_score = hn.company_sector_score(candidate, hn_cfg)

    track_terms = [
        str(x).lower()
        for x in (hn_cfg.get("track_aligned_company_terms") or [])
        if str(x).strip()
    ]
    strong_hits = [
        t
        for t in track_terms
        if t in blob_lower and t not in ("retail", "lithuania", "baltics")
    ]
    if strong_hits:
        flags.append("track_aligned")
    if "staffing" in blob_lower or "recruitment agency" in blob_lower:
        flags.append("staffing_only")
    if any(t in blob_lower for t in ("pharma", "banking", "b2b saas")):
        flags.append("wrong_sector")
    if not any(
        t in blob_lower
        for t in ("vilnius", "lithuania", "lietuva", "baltics", "kaunas")
    ):
        if profile_location and _profile_abroad(profile_location):
            flags.append("geo_mismatch")
        elif any(
            t in blob_lower
            for t in ("london", "warsaw", "berlin", "dubai", "united kingdom")
        ):
            flags.append("geo_mismatch")

    cv_block = company_validation_cfg(cv_cfg) if isinstance(cv_cfg, dict) else {}
    hard_reject_flags = [
        f
        for f in flags
        if f in {"outreach_exclude_term", "wrong_sector", "staffing_only"}
    ]
    boost, boost_label = _persona_validation_boost(
        persona=persona, cv_block=cv_block, hard_reject_flags=hard_reject_flags
    )
    # Boost is applied to the rule_score here so single-pass callers (and
    # tests) see the persona-aware score directly. validate_company strips
    # it back off before LLM blending and re-applies after, so the LLM cannot
    # undo the persona signal.
    final_score = min(100.0, sector_score + boost)

    rationale_parts = []
    if strong_hits:
        rationale_parts.append(f"Track terms: {', '.join(strong_hits[:4])}")
    if final_score >= 60:
        rationale_parts.append("Sector score supports outreach")
    elif final_score >= 40:
        rationale_parts.append("Mixed sector signals")
    else:
        rationale_parts.append("Weak sector alignment")
    if boost_label:
        rationale_parts.append(boost_label)
    if flags:
        rationale_parts.append(f"Flags: {', '.join(flags)}")

    return final_score, flags, "; ".join(rationale_parts)


def validation_status_for_row(
    *,
    sector_score: float,
    flags: list[str],
    needs_linkedin_url: bool,
    approve_threshold: float,
    review_threshold: float,
) -> str:
    hard_reject = {
        "outreach_exclude_term",
        "wrong_sector",
        "staffing_only",
    }
    if needs_linkedin_url:
        return "review"
    if any(f in hard_reject for f in flags):
        return "reject"
    if sector_score >= approve_threshold and "geo_mismatch" not in flags:
        return "approved"
    if sector_score >= review_threshold:
        return "review"
    return "reject"


def validate_company(
    company: str,
    *,
    hn_cfg: dict[str, Any],
    full_cfg: dict[str, Any],
    backend: str,
    headline: str = "",
    profile_location: str = "",
    profile_context: str = "",
    persona: str = "",
) -> tuple[float, str, list[str], str, float]:
    """Returns (final_score, web_url, flags, rationale, rule_score)."""
    if not company.strip():
        return 25.0, "", ["missing_company"], "No company name provided", 25.0

    cv_block = company_validation_cfg(full_cfg)
    llm_w = float(cv_block.get("llm_blend_weight") or 0.4)

    query = f"{company} Vilnius Lithuania luxury retail fashion operations IT careers"
    result = web_search(query, num_results=5, backend=backend)
    hits = company_site_hits(result) or result.hits[:3]
    blob = " ".join(
        f"{h.title} {h.snippet} {h.url}" for h in hits if h.title or h.snippet
    )
    if profile_context.strip():
        blob = f"{blob} {profile_context.strip()[:600]}"
    if profile_location.strip():
        blob = f"{blob} {profile_location.strip()}"
    web_url = hits[0].url if hits else ""
    rule_score, flags, rationale = score_company_from_text(
        company,
        blob,
        hn_cfg=hn_cfg,
        cv_cfg=full_cfg,
        profile_location=profile_location,
        persona=persona,
    )
    if result.error and not blob.strip():
        flags.append("web_lookup_failed")
        rationale = f"{rationale}; web lookup failed"

    # Strip persona boost so the LLM blend operates on raw sector signal.
    hard_reject_flags = [
        f
        for f in flags
        if f in {"outreach_exclude_term", "wrong_sector", "staffing_only"}
    ]
    persona_boost, _ = _persona_validation_boost(
        persona=persona, cv_block=cv_block, hard_reject_flags=hard_reject_flags
    )
    raw_rule_score = max(0.0, rule_score - persona_boost)

    final_score = rule_score
    if analyze_company and agent_enabled(full_cfg, "company_analyst"):
        analysis = analyze_company(
            company=company, headline=headline, web_blob=blob, full_cfg=full_cfg
        )
        if analysis:
            blended = (1.0 - llm_w) * raw_rule_score + llm_w * analysis.relevance_0_100
            final_score = min(100.0, blended + persona_boost)
            if analysis.rationale.strip():
                # Keep persona boost label visible after LLM rewrites rationale.
                if persona_boost > 0:
                    persona_label = persona.replace("_", " ")
                    rationale = (
                        f"{analysis.rationale.strip()}; "
                        f"{persona_label} boost (+{persona_boost:.0f})"
                    )
                else:
                    rationale = analysis.rationale.strip()
            flags = list(dict.fromkeys(flags + analysis.flags))
            if (
                analysis.recommended_status == "reject"
                and raw_rule_score < float(cv_block.get("review_threshold") or 40)
                and persona_boost <= 0
            ):
                flags.append("llm_reject")

    return final_score, web_url, flags, rationale, rule_score


def validate_rows(
    rows: list[dict[str, str]],
    *,
    hn_cfg: dict[str, Any],
    full_cfg: dict[str, Any],
    backend: str,
) -> list[dict[str, str]]:
    cv_block = company_validation_cfg(full_cfg)
    approve_threshold = float(cv_block.get("approve_threshold") or 60.0)
    review_threshold = float(cv_block.get("review_threshold") or 40.0)
    backend_pref = (
        backend if backend != "auto" else str(cv_block.get("backend") or "auto")
    )

    company_cache: dict[str, tuple[float, str, list[str], str, float]] = {}
    validated: list[dict[str, str]] = []

    for row in rows:
        out = discovery_to_validated(row)
        company = (row.get("company") or "").strip()
        headline = (row.get("headline") or "").strip()
        profile_location = (row.get("location") or "").strip()
        profile_context = (row.get("discovery_notes") or "").strip()
        persona = (row.get("persona") or "").strip()
        needs_url = (row.get("needs_linkedin_url") or "").lower() in {
            "true",
            "1",
            "yes",
        }

        cache_key = f"{company}|{profile_location}|{persona}"
        if cache_key not in company_cache:
            company_cache[cache_key] = validate_company(
                company,
                hn_cfg=hn_cfg,
                full_cfg=full_cfg,
                backend=backend_pref,
                headline=headline,
                profile_location=profile_location,
                profile_context=profile_context,
                persona=persona,
            )
        score, web_url, flags, rationale, rule_score = company_cache[cache_key]

        status = validation_status_for_row(
            sector_score=score,
            flags=flags,
            needs_linkedin_url=needs_url,
            approve_threshold=approve_threshold,
            review_threshold=review_threshold,
        )
        if status == "approved" and rule_score < approve_threshold:
            status = "review"
        out["company_relevance_score"] = f"{score:.1f}"
        out["company_rationale"] = rationale[:500]
        out["company_flags"] = ",".join(flags)
        out["company_web_url"] = web_url
        out["validation_status"] = status
        out["validated_at"] = today_iso()
        validated.append(out)

    return sort_by_rank_score(validated)


def run_validation(
    *,
    input_path: Path,
    output_path: Path,
    cfg_path: Path,
    backend: str,
    no_llm: bool = False,
    verbose_llm: bool = False,
) -> list[dict[str, str]]:
    from recruiter_ollama_client import merge_llm_runtime_flags

    full_cfg = merge_llm_runtime_flags(
        load_full_cfg(cfg_path), no_llm=no_llm, verbose_llm=verbose_llm
    )
    hn_cfg = hn.load_workflow_config(cfg_path)
    rows = read_discovery_rows(input_path)
    validated = validate_rows(rows, hn_cfg=hn_cfg, full_cfg=full_cfg, backend=backend)
    write_validated_rows(validated, output_path)
    return validated


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate company relevance for discovery CSV"
    )
    ap.add_argument("--input", type=Path, default=CANDIDATES_DISCOVERY_CSV)
    ap.add_argument("--output", type=Path, default=CANDIDATES_VALIDATED_CSV)
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument(
        "--backend",
        default="auto",
        choices=("auto", "exa", "firecrawl", "offline"),
    )
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--verbose-llm", action="store_true")
    args = ap.parse_args()

    validated = run_validation(
        input_path=args.input,
        output_path=args.output,
        cfg_path=args.config,
        backend=args.backend,
        no_llm=args.no_llm,
        verbose_llm=args.verbose_llm,
    )
    counts: dict[str, int] = {}
    for row in validated:
        status = row.get("validation_status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    print(f"Wrote {len(validated)} validated row(s) to {args.output}")
    print(f"Status counts: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
