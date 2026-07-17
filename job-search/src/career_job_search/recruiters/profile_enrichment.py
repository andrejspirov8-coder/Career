#!/usr/bin/env python3
"""Enrich validated discovery rows with fuller LinkedIn profile text before rank."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import (
    CANDIDATES_VALIDATED_CSV,
    DEFAULT_LINKEDIN_CONFIG,
)
from career_job_search.recruiters.discovery_csv import (
    read_validated_rows,
    today_iso,
    write_validated_rows,
)
from career_job_search.recruiters.web_discovery import (
    guess_company_from_snippet,
    guess_location_from_snippet,
)
from career_job_search.recruiters.web_research import (
    fetch_profile_contents,
    search_candidates_evidence_batch,
)


@dataclass
class ProfileEnrichment:
    about: str = ""
    role_text: str = ""
    headline: str = ""
    name: str = ""
    company: str = ""
    location: str = ""
    source: str = ""


def load_full_cfg(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def enrichment_cfg(full_cfg: dict[str, Any]) -> dict[str, Any]:
    return full_cfg.get("profile_enrichment") or {}


def _looks_like_company_about(text: str) -> bool:
    """Detect LinkedIn About sections that describe the employer, not the person."""
    t = (text or "").lower()
    if len(t) < 40:
        return False
    markers = (
        "our software",
        "we build",
        "full-stack development",
        "our engineers",
        "our company",
        "we are a",
        "we're a",
    )
    return any(m in t for m in markers)


def parse_exa_profile_text(text: str) -> ProfileEnrichment:
    raw = (text or "").strip()
    about = ""
    role = ""
    section_break = r"(?=\n## [^#\n]|\Z)"
    about_match = re.search(rf"## About\s*(.*?){section_break}", raw, re.S | re.I)
    if about_match:
        about = about_match.group(1).strip()
    exp_match = re.search(rf"## Experience\s*(.*?){section_break}", raw, re.S | re.I)
    if exp_match:
        role = exp_match.group(1).strip()
    if not about and not role:
        about = raw
    headline = ""
    name = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not name:
            name = re.sub(r"\s*[\|\-–—].*$", "", line).strip()[:120]
            continue
        if not headline and line != name:
            headline = line[:220]
            break
    if not role and headline:
        role = headline
    if _looks_like_company_about(about) and headline:
        if not role or role == about[:220]:
            role = headline
        about = headline
    company = guess_company_from_snippet(raw)
    location = guess_location_from_snippet(raw)
    return ProfileEnrichment(
        about=about[:2400],
        role_text=role[:2400],
        headline=headline,
        name=name,
        company=company,
        location=location,
        source="web_exa",
    )


def parse_playwright_payload(payload: dict[str, Any]) -> ProfileEnrichment:
    about = str(payload.get("about") or "").strip()[:2400]
    role = str(payload.get("role_text") or "").strip()[:2400]
    return ProfileEnrichment(
        about=about,
        role_text=role,
        headline=str(payload.get("headline") or "").strip()[:220],
        name=str(payload.get("name") or "").strip()[:120],
        company=str(payload.get("companyGuess") or "").strip()[:120],
        location=str(payload.get("location") or "").strip()[:120],
        source="browser",
    )


def row_needs_enrichment(row: dict[str, str], *, min_chars: int) -> bool:
    if len((row.get("enriched_about") or "").strip()) >= min_chars:
        return False
    status = (row.get("validation_status") or "").strip().lower()
    return status in {"approved", "review"}


def apply_enrichment(
    row: dict[str, str], enrichment: ProfileEnrichment
) -> dict[str, str]:
    out = dict(row)
    if enrichment.name and not (out.get("name") or "").strip():
        out["name"] = enrichment.name
    if enrichment.headline:
        out["headline"] = enrichment.headline
    if enrichment.company and (
        not (out.get("company") or "").strip()
        or len(out.get("company") or "") < len(enrichment.company)
    ):
        out["company"] = enrichment.company
    if enrichment.location:
        out["location"] = enrichment.location
    if enrichment.about:
        out["enriched_about"] = enrichment.about
    if enrichment.role_text:
        out["enriched_role_text"] = enrichment.role_text
    if enrichment.about or enrichment.role_text:
        out["enriched_at"] = today_iso()
    return out


def enrich_rows_with_exa(
    rows: list[dict[str, str]],
    *,
    backend: str,
    max_characters: int,
    min_chars: int,
    allowed_statuses: set[str],
) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    targets: list[dict[str, str]] = []
    for row in rows:
        status = (row.get("validation_status") or "").strip().lower()
        if status not in allowed_statuses:
            continue
        if not row_needs_enrichment(row, min_chars=min_chars):
            continue
        url = lis.canonical_profile_url(row.get("profile_url") or "") or ""
        if url:
            targets.append(row)

    if not targets:
        return rows, errors

    url_list = [
        lis.canonical_profile_url(r.get("profile_url") or "")
        or r.get("profile_url")
        or ""
        for r in targets
    ]
    contents = fetch_profile_contents(
        url_list, backend=backend, max_characters=max_characters
    )
    if not contents:
        errors.append("profile enrichment: no Exa contents returned")
        return rows, errors

    by_url = {lis.canonical_profile_url(u) or u: text for u, text in contents.items()}
    updated: list[dict[str, str]] = []
    for row in rows:
        url = lis.canonical_profile_url(row.get("profile_url") or "") or ""
        text = by_url.get(url, "")
        if text:
            updated.append(apply_enrichment(row, parse_exa_profile_text(text)))
        else:
            updated.append(row)
    return updated, errors


def enrich_rows_with_browser(
    rows: list[dict[str, str]],
    *,
    full_cfg: dict[str, Any],
    headed: bool,
    min_chars: int,
    allowed_statuses: set[str],
) -> tuple[list[dict[str, str]], list[str]]:
    from playwright.sync_api import sync_playwright

    from career_job_search.integrations.linkedin.campaign import (
        action_delay,
        automation_evaluate_or_closed,
        automation_goto_or_closed,
        between_profiles_delay,
        cfg_limits,
        dwell_navigation,
        launch_linkedin_browser_context,
        resolve_browser_channel,
    )

    errors: list[str] = []
    targets = [
        row
        for row in rows
        if (row.get("validation_status") or "").strip().lower() in allowed_statuses
        and row_needs_enrichment(row, min_chars=min_chars)
    ]
    if not targets:
        return rows, errors

    limits = cfg_limits(full_cfg)
    channel = resolve_browser_channel(full_cfg, None)
    by_url: dict[str, ProfileEnrichment] = {}

    with sync_playwright() as playwright:
        ctx = launch_linkedin_browser_context(
            playwright, headed=headed, channel=channel
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        from career_job_search.integrations.linkedin.browser import (
            PlaywrightLinkedInAutomator,
        )

        automation = PlaywrightLinkedInAutomator(page, limits=limits)
        for idx, row in enumerate(targets):
            url = lis.canonical_profile_url(row.get("profile_url") or "") or ""
            if not url:
                continue
            if idx > 0:
                between_profiles_delay(limits)
            if not automation_goto_or_closed(automation, url):
                errors.append(f"browser closed while enriching {url}")
                break
            action_delay(limits)
            dwell_navigation(limits)
            payload = automation_evaluate_or_closed(automation, lis.PROFILE_SCRAPER_JS)
            if payload is None:
                errors.append(f"browser closed while scraping {url}")
                break
            if isinstance(payload, dict):
                by_url[url] = parse_playwright_payload(payload)
        try:
            ctx.close()
        except Exception:
            pass

    updated: list[dict[str, str]] = []
    for row in rows:
        url = lis.canonical_profile_url(row.get("profile_url") or "") or ""
        enrichment = by_url.get(url)
        if enrichment and (enrichment.about or enrichment.role_text):
            updated.append(apply_enrichment(row, enrichment))
        else:
            updated.append(row)
    return updated, errors


def deepen_candidate_evidence(
    rows: list[dict[str, str]],
    *,
    full_cfg: dict[str, Any],
    backend: str = "auto",
) -> tuple[list[dict[str, str]], list[str]]:
    """Run targeted Exa search per approved candidate to deepen evidence.

    After standard enrichment fills ``enriched_about`` / ``enriched_role_text``
    from the LinkedIn profile page text, this runs an additional *search*
    (not contents fetch) targeting pages that mention the candidate in a
    hiring/HR context. The goal is to surface snippets like "HR Manager at
    Apranga" or "Recruiter at LPP" that the outreach writer can reference.

    Results are stored in ``evidence_deepen_text`` and
    ``evidence_deepen_keywords`` CSV columns. The outreach writer's
    ``lookup_candidate_evidence()`` tool reads these columns.
    """
    block = enrichment_cfg(full_cfg)
    deepen_cfg = block.get("evidence_deepen") or {}
    if not bool(deepen_cfg.get("enabled", True)):
        return rows, []

    max_chars = int(deepen_cfg.get("max_characters") or 1500)
    search_suffix = str(deepen_cfg.get("search_suffix") or "hiring talent recruiter")
    statuses = {
        str(s).strip().lower()
        for s in (deepen_cfg.get("only_statuses") or ["approved"])
        if str(s).strip()
    }
    errors: list[str] = []

    # Build candidate list: approved/review rows that have profile URLs
    candidates = []
    for row in rows:
        status = (row.get("validation_status") or "").strip().lower()
        if status not in statuses:
            continue
        url = (row.get("profile_url") or "").strip()
        if url:
            candidates.append(row)

    if not candidates:
        return rows, errors

    results = search_candidates_evidence_batch(
        candidates,
        search_suffix=search_suffix,
        max_characters=max_chars,
        backend=backend,
    )
    if not results:
        return rows, errors

    updated: list[dict[str, str]] = []
    for row in rows:
        url = (row.get("profile_url") or "").strip()
        evidence = results.get(url)
        if evidence and evidence.personalization_text:
            row = dict(row)
            existing_text = (row.get("evidence_deepen_text") or "").strip()
            if not existing_text:
                row["evidence_deepen_text"] = evidence.personalization_text
                row["evidence_deepen_keywords"] = evidence.sourcing_keywords
                row["evidence_deepen_source"] = evidence.source
                row["enriched_at"] = row.get("enriched_at") or today_iso()
        updated.append(row)

    return updated, errors


def enrich_validated_rows(
    rows: list[dict[str, str]],
    *,
    full_cfg: dict[str, Any],
    backend: str = "auto",
    use_browser: bool = False,
    headed: bool = True,
) -> tuple[list[dict[str, str]], list[str]]:
    block = enrichment_cfg(full_cfg)
    if not bool(block.get("enabled", True)):
        return rows, []

    max_chars = int(block.get("max_characters") or 3000)
    min_chars = int(block.get("min_enriched_chars") or 180)
    max_rows = int(block.get("max_profiles_per_run") or 10)
    statuses = {
        str(s).strip().lower()
        for s in (block.get("only_statuses") or ["approved", "review"])
        if str(s).strip()
    }
    backend_pref = backend if backend != "auto" else str(block.get("backend") or "exa")
    mode = str(block.get("mode") or "exa").lower()
    if use_browser:
        mode = "browser"

    eligible = [
        row
        for row in rows
        if (row.get("validation_status") or "").strip().lower() in statuses
        and row_needs_enrichment(row, min_chars=min_chars)
    ][:max_rows]
    if not eligible:
        return rows, []

    errors: list[str] = []
    if mode in {"browser", "playwright"}:
        rows, browser_errors = enrich_rows_with_browser(
            rows,
            full_cfg=full_cfg,
            headed=headed,
            min_chars=min_chars,
            allowed_statuses=statuses,
        )
        errors.extend(browser_errors)
    else:
        # Legacy: sync Exa /contents endpoint + regex parsing
        rows, exa_errors = enrich_rows_with_exa(
            rows,
            backend=backend_pref,
            max_characters=max_chars,
            min_chars=min_chars,
            allowed_statuses=statuses,
        )
        errors.extend(exa_errors)
        if mode == "auto":
            short_rows = [
                row
                for row in rows
                if (row.get("validation_status") or "").strip().lower() in statuses
                and row_needs_enrichment(row, min_chars=min_chars)
            ]
            if short_rows and use_browser:
                rows, browser_errors = enrich_rows_with_browser(
                    rows,
                    full_cfg=full_cfg,
                    headed=headed,
                    min_chars=min_chars,
                    allowed_statuses=statuses,
                )
                errors.extend(browser_errors)

    # Step 2: deepen evidence for approved candidates (Branch H)
    rows, deepen_errors = deepen_candidate_evidence(
        rows, full_cfg=full_cfg, backend=backend_pref
    )
    errors.extend(deepen_errors)

    return rows, errors


def run_enrichment(
    *,
    input_path: Path,
    output_path: Path,
    cfg_path: Path,
    backend: str = "auto",
    use_browser: bool = False,
    headed: bool = True,
) -> tuple[list[dict[str, str]], list[str]]:
    full_cfg = load_full_cfg(cfg_path)
    rows = read_validated_rows(input_path)
    enriched, errors = enrich_validated_rows(
        rows,
        full_cfg=full_cfg,
        backend=backend,
        use_browser=use_browser,
        headed=headed,
    )
    write_validated_rows(enriched, output_path)
    return enriched, errors


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Enrich validated CSV rows with profile text"
    )
    ap.add_argument("--input", type=Path, default=CANDIDATES_VALIDATED_CSV)
    ap.add_argument("--output", type=Path, default=CANDIDATES_VALIDATED_CSV)
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument(
        "--backend",
        default="auto",
        choices=("auto", "exa", "firecrawl", "offline"),
    )
    ap.add_argument(
        "--browser", action="store_true", help="Use Playwright profile scrape"
    )
    ap.add_argument("--headed", default=True, action=argparse.BooleanOptionalAction)
    args = ap.parse_args()
    rows, errors = run_enrichment(
        input_path=args.input,
        output_path=args.output,
        cfg_path=args.config,
        backend=args.backend,
        use_browser=args.browser,
        headed=args.headed,
    )
    enriched_count = sum(1 for r in rows if (r.get("enriched_at") or "").strip())
    print(f"Enriched rows with timestamp: {enriched_count}")
    for err in errors[:5]:
        print(f"warn: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
