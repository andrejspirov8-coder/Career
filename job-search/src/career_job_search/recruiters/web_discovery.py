#!/usr/bin/env python3
"""Web-first discovery: research hiring leaders, resolve LinkedIn URLs, draft rank CSV."""

from __future__ import annotations

import argparse
import importlib
import re
from pathlib import Path
from typing import Any

import yaml

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.campaign import read_seen_profile_urls
from career_job_search.integrations.linkedin.paths import (
    CANDIDATES_DISCOVERY_CSV,
    DEFAULT_LINKEDIN_CONFIG,
    MCP_DISCOVERY_BATCH_JSONL,
    RECRUITERS_CSV,
)
from career_job_search.recruiters.agent_models import DiscoveryExtraction
from career_job_search.recruiters.discovery_csv import (
    discovery_row_partial,
    read_discovery_rows,
    sort_by_rank_score,
    today_iso,
    write_discovery_rows,
)
from career_job_search.recruiters.hiring_models import HistorySignals, ProfileCandidate
from career_job_search.recruiters.matching import match_recruiter_profile
from career_job_search.recruiters.ollama_agents import extract_discovery_batch
from career_job_search.recruiters.ollama_client import (
    agent_cfg,
    agent_enabled,
    llm_enabled,
)
from career_job_search.recruiters.web_research import (
    WebSearchHit,
    linkedin_profile_hits,
    web_search,
)

_LINKEDIN_IN_RE = re.compile(r"https?://(?:[\w.-]+\.)?linkedin\.com/in/[\w%-]+/?", re.I)


def load_full_cfg(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def web_discovery_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("web_discovery") or {}


def discovery_geo_scope(full_cfg: dict[str, Any]) -> str:
    return str(web_discovery_cfg(full_cfg).get("geo_scope") or "vilnius").lower()


def discovery_requires_geo_match(full_cfg: dict[str, Any]) -> bool:
    return bool(web_discovery_cfg(full_cfg).get("require_geo_match", False))


def linkedin_discovery_query(base_query: str, full_cfg: dict[str, Any]) -> str:
    suffix = str(
        web_discovery_cfg(full_cfg).get("query_geo_suffix") or "Vilnius Lithuania"
    ).strip()
    return f"{base_query} site:linkedin.com/in {suffix}"


def location_is_abroad(location: str) -> bool:
    return bool(
        re.search(
            r"\((US|FI|ES|LV|DE|GB|UK)\)|United States|Boston|New York|"
            r"Helsinki|Spain|Riga, Latvia|Greater .* Area \(US\)|"
            r"Las Vegas|Bentonville|Reno",
            location or "",
            re.I,
        )
    )


def passes_geo_filter(location: str, snippet: str, *, scope: str) -> bool:
    if location_is_abroad(location):
        return False
    blob = f"{location} {snippet}".lower()
    if scope in ("none", "off", ""):
        return True
    if scope == "lithuania":
        return bool(
            re.search(
                r"\b(vilnius|vilniaus|kaunas|klaip[eė]da|lithuania|lietuva)\b",
                blob,
                re.I,
            )
        )
    return bool(re.search(r"\b(vilnius|vilniaus)\b", blob, re.I))


def discovery_queries(cfg: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (variant_slug, query) pairs from config."""
    block = web_discovery_cfg(cfg)
    out: list[tuple[str, str]] = []
    by_variant = block.get("queries_by_variant") or {}
    if isinstance(by_variant, dict):
        for variant, queries in by_variant.items():
            if not isinstance(queries, list):
                continue
            for q in queries:
                qline = str(q).strip()
                if qline:
                    out.append((str(variant), qline))
    flat = block.get("queries") or []
    if isinstance(flat, list):
        for q in flat:
            qline = str(q).strip()
            if qline:
                out.append(("luxury-retail", qline))
    return out


def discovery_query_plan(
    cfg: dict[str, Any],
    *,
    opportunity_db_path: Path | str,
    now: Any | None = None,
) -> list[tuple[str, str]]:
    """Return (variant_slug, query) plan: opportunity targets first, then generic.

    Opportunity-company queries (with their CV variant) are placed ahead of the
    configured generic per-variant queries so verified hiring companies are
    discovered first, within the configured company/queries budget.
    """
    from career_job_search.recruiters.opportunity_targets import (
        opportunity_target_queries,
        opportunity_target_settings,
        safe_load_opportunity_targets,
    )

    plan: list[tuple[str, str]] = []
    settings = opportunity_target_settings(cfg)
    if settings.enabled:
        targets, _ = safe_load_opportunity_targets(
            db_path=opportunity_db_path,
            settings=settings,
            now=now,
        )
        plan = opportunity_target_queries(
            targets,
            queries_per_company=settings.queries_per_company,
        )
    return plan + discovery_queries(cfg)


def extract_linkedin_url(text: str) -> str:
    match = _LINKEDIN_IN_RE.search(text or "")
    if not match:
        return ""
    return lis.canonical_profile_url(match.group(0)) or match.group(0)


def guess_name_from_title(title: str) -> str:
    title = re.sub(r"\s*[\|\-–—].*$", "", title or "").strip()
    title = re.sub(r"\s+on LinkedIn.*$", "", title, flags=re.I).strip()
    return title[:120]


_GENERIC_LT_LOCATIONS = frozenset(
    {"lithuania", "vilnius", "vilnius, lithuania", "kaunas", "kaunas, lithuania"}
)


def _is_generic_lt_location(location: str) -> bool:
    return (location or "").strip().lower() in _GENERIC_LT_LOCATIONS


def guess_location_from_snippet(snippet: str) -> str:
    """Parse LinkedIn-style location lines from Exa/web snippets."""
    text = snippet or ""
    inline = re.search(
        r"\bin\s+((?:Vilnius|Vilniaus|Kaunas|Klaipėda|Klaipeda)[^,\n]*,\s*Lithuania)\b",
        text,
        re.I,
    )
    if inline:
        loc = inline.group(1).strip()
        return loc.replace("Vilniaus", "Vilnius")[:120]

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        lower = line.lower()
        if line.startswith("#") or "connections" in lower or "followers" in lower:
            continue
        if re.search(
            r"\b(present|\d{4})\b.*\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
            lower,
        ):
            continue
        if re.search(r"\([A-Z]{2}\)\s*$", line):
            return line[:120]
        if idx > 0 and " at " in lines[idx - 1].lower():
            if "," in line or re.search(r"\b(area|metropolitan)\b", lower):
                return line[:120]
        if re.search(
            r"\b(vilnius|kaunas|lithuania|lietuva|riga|latvia|tallinn)\b", lower
        ):
            return line[:120]
    return ""


def _looks_like_job_title_fragment(company: str) -> bool:
    lower = (company or "").lower()
    if not company or len(company) < 3:
        return True
    if "|" in company or company.startswith("ional "):
        return True
    title_markers = (
        "sales & distribution",
        "b2b sales",
        "independent sales",
        "management ...",
    )
    return any(marker in lower for marker in title_markers)


def guess_company_from_snippet(snippet: str) -> str:
    for line in (snippet or "").splitlines():
        bracket = re.search(r"\bat\s+\[([^\]]+)\]", line, re.I)
        if bracket:
            return bracket.group(1).strip()[:120]
        plain = re.search(
            r"\b(?:Manager|Director|Head|VP|Lead|Officer|President)\b.*?\bat\s+([^\n\r\[\(]+)",
            line,
            re.I,
        )
        if plain:
            return plain.group(1).strip()[:120]
        simple = re.search(r"\bat\s+([A-Za-z0-9][^\n\r\[\(]{1,80})", line, re.I)
        if simple:
            return simple.group(1).strip()[:120]
    return ""


def guess_company_from_hit(hit: WebSearchHit) -> str:
    title = hit.title or ""
    if " at " in title:
        after_at = title.split(" at ", 1)[1]
        company = re.sub(r"\s*[\|\-–—].*$", "", after_at).strip()
        company = re.sub(r"\s*-?\s*LinkedIn\s*$", "", company, flags=re.I).strip()
        if company and "linkedin" not in company.lower():
            return company[:120]
    from_snippet = guess_company_from_snippet(hit.snippet or "")
    if from_snippet and not _looks_like_job_title_fragment(from_snippet):
        return from_snippet
    blob = f"{title} {hit.snippet}".lower()
    for marker in (" at ", " @ ", " — ", " – "):
        if marker.strip() in blob:
            parts = re.split(re.escape(marker.strip()), title, maxsplit=1, flags=re.I)
            if len(parts) == 2:
                candidate = parts[1].strip()
                candidate = re.sub(r"\s*[\|\-–—].*$", "", candidate).strip()
                if candidate and "linkedin" not in candidate.lower():
                    return candidate[:120]
    return ""


def draft_rank_fields(
    *,
    name: str,
    headline: str,
    company: str,
    location: str,
    profile_url: str,
    variant_slug: str,
    hn_cfg: dict[str, Any],
    full_cfg: dict[str, Any],
    discovery_notes: str = "",
) -> tuple[str, str, str, str]:
    scoring = match_recruiter_profile(
        headline=headline or name or "professional",
        name=name,
        profile_url=profile_url or "https://www.linkedin.com/in/unknown/",
        company=company,
        about="",
        role_text=headline,
        location=location,
        recruiter_cfg=full_cfg,
    )
    rec = scoring.get("recommendation") or {}
    best_variant = str(rec.get("variant_slug") or variant_slug or "luxury-retail")
    cv_score = str(rec.get("primary_score") or "")

    profile_blob = "\n".join(
        x for x in (headline, (discovery_notes or "")[:400]) if x.strip()
    )
    hiring = importlib.import_module("career_job_search.recruiters.hiring_network")
    candidate = ProfileCandidate(
        profile_url=profile_url or "https://www.linkedin.com/in/unknown/",
        name=name,
        headline=headline,
        company=company,
        location=location,
        scraped_text=profile_blob,
        search_variant_slug=variant_slug,
    )
    persona_dec = hiring.classify_persona(candidate, hn_cfg)
    cv_dec = hiring.match_candidate_to_cv(candidate, hn_cfg)
    rank_score = hiring.rank_candidate(
        candidate, persona_dec, cv_dec, hn_cfg, HistorySignals()
    )
    return best_variant, cv_score, persona_dec.persona, f"{rank_score:.2f}"


def _merge_llm_extraction(
    *,
    name: str,
    headline: str,
    company: str,
    profile_url: str,
    location: str,
    discovery_notes: str,
    extraction: DiscoveryExtraction | None,
) -> tuple[str, str, str, str, str, str]:
    if not extraction:
        return name, headline, company, profile_url, location, discovery_notes
    if extraction.name.strip():
        name = extraction.name.strip()
    if extraction.headline.strip():
        headline = extraction.headline.strip()[:220]
    if extraction.company.strip():
        company = extraction.company.strip()[:120]
    url = extract_linkedin_url(extraction.profile_url) or profile_url
    if extraction.location.strip():
        llm_location = extraction.location.strip()
        if (
            _is_generic_lt_location(llm_location)
            and location.strip()
            and not _is_generic_lt_location(location)
        ):
            pass
        else:
            location = llm_location
    if extraction.discovery_notes.strip():
        discovery_notes = extraction.discovery_notes.strip()[:400]
    return name, headline, company, url, location, discovery_notes


def hit_to_discovery_row(
    hit: WebSearchHit,
    *,
    variant_slug: str,
    hn_cfg: dict[str, Any],
    full_cfg: dict[str, Any],
    seen_urls: set[str],
    backend: str,
    llm_extraction: DiscoveryExtraction | None = None,
    geo_scope_override: str | None = None,
) -> dict[str, str] | None:
    profile_url = extract_linkedin_url(hit.url) or extract_linkedin_url(hit.snippet)
    if profile_url and profile_url in seen_urls:
        return None

    name = guess_name_from_title(hit.title)
    headline = hit.title[:220]
    company = guess_company_from_hit(hit)
    location = guess_location_from_snippet(hit.snippet or "")
    discovery_notes = (hit.snippet or "")[:400]

    regex_first = agent_cfg(full_cfg, "discovery").get("regex_first", True)
    use_llm = llm_extraction is not None and (
        not regex_first or not profile_url or not name or not company
    )
    if llm_extraction and (use_llm or not regex_first):
        name, headline, company, profile_url, location, discovery_notes = (
            _merge_llm_extraction(
                name=name,
                headline=headline,
                company=company,
                profile_url=profile_url or "",
                location=location,
                discovery_notes=discovery_notes,
                extraction=llm_extraction,
            )
        )

    needs_url = not bool(profile_url)

    if profile_url:
        try:
            best_variant, cv_score, persona, rank_draft = draft_rank_fields(
                name=name,
                headline=headline,
                company=company,
                location=location,
                profile_url=profile_url,
                variant_slug=variant_slug,
                hn_cfg=hn_cfg,
                full_cfg=full_cfg,
                discovery_notes=discovery_notes,
            )
        except ValueError:
            return None
    else:
        best_variant = variant_slug
        cv_score = ""
        persona = ""
        rank_draft = ""

    row = discovery_row_partial(
        profile_url=profile_url,
        name=name,
        headline=headline,
        company=company,
        location=location,
        company_source_url=hit.url,
        discovery_source=backend,
        source_backend=hit.source or backend,
        discovery_notes=discovery_notes,
        variant_slug=best_variant,
        cv_score=cv_score,
        persona=persona,
        rank_score_draft=rank_draft,
        search_intent="hiring_leader",
        needs_linkedin_url="true" if needs_url else "false",
        discovered_at=today_iso(),
    )
    if profile_url:
        seen_urls.add(profile_url)
    scope = (geo_scope_override or "").strip() or discovery_geo_scope(full_cfg)
    if discovery_requires_geo_match(full_cfg) and not passes_geo_filter(
        location, hit.snippet or "", scope=scope
    ):
        return None
    return row


def merge_mcp_batch(
    rows: list[dict[str, str]], *, hn_cfg: dict[str, Any], full_cfg: dict[str, Any]
) -> list[dict[str, str]]:
    if not MCP_DISCOVERY_BATCH_JSONL.is_file():
        return rows
    import json

    seen = {lis.canonical_profile_url(r.get("profile_url") or "") for r in rows}
    seen.discard("")
    for line in MCP_DISCOVERY_BATCH_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        stub = json.loads(line)
        url = lis.canonical_profile_url(stub.get("profile_url") or "") or ""
        if not url or url in seen:
            continue
        try:
            mcp_notes = " ".join(
                str(stub.get(k) or "")
                for k in ("about", "headline", "role_text")
                if str(stub.get(k) or "").strip()
            )[:400]
            best_variant, cv_score, persona, rank_draft = draft_rank_fields(
                name=str(stub.get("name") or ""),
                headline=str(stub.get("headline") or ""),
                company=str(stub.get("company") or ""),
                location=str(stub.get("location") or "Lithuania"),
                profile_url=url,
                variant_slug=str(stub.get("variant_slug") or "luxury-retail"),
                hn_cfg=hn_cfg,
                full_cfg=full_cfg,
                discovery_notes=mcp_notes,
            )
        except ValueError:
            continue
        rows.append(
            discovery_row_partial(
                profile_url=url,
                name=str(stub.get("name") or ""),
                headline=str(stub.get("headline") or ""),
                company=str(stub.get("company") or ""),
                location=str(stub.get("location") or ""),
                company_source_url="",
                discovery_source="mcp_manual",
                discovery_notes="Merged from mcp_discovery_batch.jsonl",
                variant_slug=best_variant,
                cv_score=cv_score,
                persona=persona,
                rank_score_draft=rank_draft,
                search_intent=str(stub.get("search_intent") or "hiring_leader"),
                needs_linkedin_url="false",
                discovered_at=today_iso(),
            )
        )
        seen.add(url)
    return rows


def run_discovery(
    *,
    cfg_path: Path,
    output_path: Path,
    backend: str = "auto",
    max_per_query: int = 5,
    merge_mcp: bool = True,
    append: bool = False,
    no_llm: bool = False,
    verbose_llm: bool = False,
    use_cache: bool = True,
) -> tuple[list[dict[str, str]], list[str]]:
    from career_job_search.recruiters.ollama_client import merge_llm_runtime_flags

    full_cfg = merge_llm_runtime_flags(
        load_full_cfg(cfg_path), no_llm=no_llm, verbose_llm=verbose_llm
    )
    hiring = importlib.import_module("career_job_search.recruiters.hiring_network")
    hn_cfg = hiring.load_workflow_config(cfg_path)
    wd_cfg = web_discovery_cfg(full_cfg)
    backend_pref = (
        backend if backend != "auto" else str(wd_cfg.get("backend") or "auto")
    )
    max_per_query = int(wd_cfg.get("max_results_per_query") or max_per_query)
    max_rows_per_run = int(wd_cfg.get("discovery_max_rows_per_run") or 0)
    geo_fallback = str(wd_cfg.get("geo_scope_fallback") or "").strip().lower()
    primary_geo_scope = discovery_geo_scope(full_cfg)

    seen_urls: set[str] = set(read_seen_profile_urls(RECRUITERS_CSV))
    existing = read_discovery_rows(output_path) if append else []
    for row in existing:
        canon = lis.canonical_profile_url(row.get("profile_url") or "") or ""
        if canon:
            seen_urls.add(canon)

    rows: list[dict[str, str]] = list(existing) if append else []
    errors: list[str] = []

    def _append_hits(
        hits_slice: list,
        *,
        variant_slug: str,
        result_backend: str,
        geo_scope: str,
    ) -> int:
        nonlocal rows
        if not hits_slice:
            return 0
        llm_extractions: list[DiscoveryExtraction] = []
        if llm_enabled(full_cfg) and agent_enabled(full_cfg, "discovery"):
            llm_extractions = extract_discovery_batch(
                hits_slice, variant_slug=variant_slug, full_cfg=full_cfg
            )
        added = 0
        for idx, hit in enumerate(hits_slice):
            extraction = llm_extractions[idx] if idx < len(llm_extractions) else None
            row = hit_to_discovery_row(
                hit,
                variant_slug=variant_slug,
                hn_cfg=hn_cfg,
                full_cfg=full_cfg,
                seen_urls=seen_urls,
                backend=result_backend,
                llm_extraction=extraction,
                geo_scope_override=geo_scope,
            )
            if row:
                rows.append(row)
                added += 1
                if max_rows_per_run and len(rows) >= max_rows_per_run:
                    break
        return added

    for variant_slug, query in discovery_queries(full_cfg):
        if max_rows_per_run and len(rows) >= max_rows_per_run:
            break
        linkedin_query = linkedin_discovery_query(query, full_cfg)
        result = web_search(
            linkedin_query,
            num_results=max_per_query,
            backend=backend_pref,
            full_cfg=full_cfg,
            use_cache=use_cache,
        )
        if result.error:
            errors.append(f"{query}: {result.error}")
        profile_hits = linkedin_profile_hits(result)
        if not profile_hits and result.hits:
            profile_hits = result.hits[:max_per_query]
        hits_slice = profile_hits[:max_per_query]
        backend_label = result.backend or backend_pref
        added = _append_hits(
            hits_slice,
            variant_slug=variant_slug,
            result_backend=backend_label,
            geo_scope=primary_geo_scope,
        )
        if (
            added == 0
            and hits_slice
            and geo_fallback
            and geo_fallback != primary_geo_scope
            and discovery_requires_geo_match(full_cfg)
        ):
            _append_hits(
                hits_slice,
                variant_slug=variant_slug,
                result_backend=backend_label,
                geo_scope=geo_fallback,
            )
        if max_rows_per_run and len(rows) >= max_rows_per_run:
            break

    if merge_mcp:
        rows = merge_mcp_batch(rows, hn_cfg=hn_cfg, full_cfg=full_cfg)

    rows = sort_by_rank_score(rows)
    write_discovery_rows(rows, output_path)
    return rows, errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Web-first recruiter discovery")
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument("--output", type=Path, default=CANDIDATES_DISCOVERY_CSV)
    ap.add_argument(
        "--backend",
        default="auto",
        choices=("auto", "exa", "firecrawl", "offline"),
    )
    ap.add_argument("--max-per-query", type=int, default=5)
    ap.add_argument("--no-merge-mcp", action="store_true")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--verbose-llm", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    rows, errors = run_discovery(
        cfg_path=args.config,
        output_path=args.output,
        backend=args.backend,
        max_per_query=args.max_per_query,
        merge_mcp=not args.no_merge_mcp,
        append=args.append,
        no_llm=args.no_llm,
        verbose_llm=args.verbose_llm,
        use_cache=not args.no_cache,
    )
    with_url = sum(1 for r in rows if (r.get("profile_url") or "").strip())
    needs_url = sum(
        1 for r in rows if (r.get("needs_linkedin_url") or "").lower() == "true"
    )
    print(f"Wrote {len(rows)} discovery row(s) to {args.output}")
    print(f"With profile_url: {with_url}; needs_linkedin_url: {needs_url}")
    for err in errors:
        print(f"WARN: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
