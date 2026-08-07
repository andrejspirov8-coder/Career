"""Read-only LinkedIn job-listing discovery for the opportunity pipeline.

This adapter uses a separate persistent browser profile and only reads public
job-search and job-detail pages. It never sends messages, applies to jobs,
uploads files, bypasses access controls, or handles CAPTCHA screens.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from career_job_search.core.paths import project_path
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
    normalise_url,
    utc_now_iso,
)
from career_job_search.opportunities.normalization import (
    canonical_linkedin_job_url,
    infer_remote_policy,
    linkedin_job_id_from_url,
)

JOB_ROOT = project_path()

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:  # pragma: no cover - exercised only in incomplete installs
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment,misc]
    sync_playwright = None  # type: ignore[assignment]

DEFAULT_PROFILE_DIR = project_path("linkedin", ".jobs-browser-profile")
ACCESS_PATH_MARKERS = ("/login", "/checkpoint", "/challenge", "/authwall")
ACCESS_TEXT_MARKERS = (
    "verify you're human",
    "security verification",
    "unusual activity",
    "captcha",
)
NO_RESULTS_MARKERS = (
    "no matching jobs",
    "no jobs found",
    "we couldn't find any jobs",
    "no results",
)


class LinkedInScrapeError(RuntimeError):
    """A safe, actionable LinkedIn discovery failure."""


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _int_setting(value: object, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(value or default))
    except (TypeError, ValueError):
        return default


def _queries(source_config: dict[str, Any]) -> list[str]:
    raw = source_config.get("queries") or []
    values = [str(item).strip() for item in raw if str(item).strip()]
    if values:
        return values
    by_variant = source_config.get("queries_by_variant") or {}
    if isinstance(by_variant, dict):
        for items in by_variant.values():
            if isinstance(items, list):
                values.extend(str(item).strip() for item in items if str(item).strip())
    return list(dict.fromkeys(values))


def build_search_url(
    *,
    base_url: str,
    keywords: str,
    location: str,
    posted_within_hours: int,
    page_number: int = 0,
) -> str:
    base = base_url.rstrip("/") + "/jobs/search/"
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": f"r{posted_within_hours * 3600}",
        "position": "1",
        "pageNum": str(page_number),
        "start": str(page_number * 25),
    }
    return f"{base}?{urlencode(params)}"


job_id_from_url = linkedin_job_id_from_url


def canonical_job_url(url: str) -> str:
    return canonical_linkedin_job_url(
        url,
        normalize_url=normalise_url,
        require_linkedin_host=False,
    )


def access_block_reason(current_url: str, visible_text: str, *, cards: int) -> str:
    lowered_url = (current_url or "").casefold()
    lowered_text = (visible_text or "").casefold()
    for marker in ACCESS_PATH_MARKERS:
        if marker in lowered_url:
            return f"linkedin_access_wall:{marker.lstrip('/')}"
    for marker in ACCESS_TEXT_MARKERS:
        if marker in lowered_text:
            return f"linkedin_access_wall:{marker}"
    if cards == 0 and "sign in" in lowered_text and "join linkedin" in lowered_text:
        return "linkedin_login_wall"
    return ""


def _first_text(container: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            locator = container.locator(selector)
            if locator.count() > 0:
                value = _clean_text(locator.first.inner_text(timeout=900))
                if value:
                    return value
        except Exception:  # noqa: S112
            continue
    return ""


def _card_container(anchor: Any) -> Any:
    for selector in (
        "xpath=ancestor::li[1]",
        "xpath=ancestor::*[contains(@class, 'base-card')][1]",
    ):
        try:
            candidate = anchor.locator(selector)
            if candidate.count() > 0:
                return candidate.first
        except Exception:  # noqa: S112
            continue
    return anchor


def extract_job_cards(
    page: Any,
    *,
    query: str,
    max_results: int,
) -> list[dict[str, str]]:
    anchors = page.locator("a[href*='/jobs/view/']")
    cards: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index in range(min(anchors.count(), max_results * 3)):
        anchor = anchors.nth(index)
        try:
            href = str(anchor.get_attribute("href") or "")
        except Exception:  # noqa: S112
            continue
        url = canonical_job_url(href)
        job_id = job_id_from_url(url)
        if not url or not job_id or job_id in seen_ids:
            continue
        container = _card_container(anchor)
        title = _first_text(
            container,
            (".base-search-card__title", ".job-card-list__title", "h3"),
        )
        company = _first_text(
            container,
            (".base-search-card__subtitle", ".job-card-container__company-name", "h4"),
        )
        location = _first_text(
            container,
            (
                ".job-search-card__location",
                ".job-card-container__metadata-item",
                ".base-search-card__metadata",
            ),
        )
        try:
            card_text = _clean_text(container.inner_text(timeout=900))
        except Exception:
            card_text = _clean_text(anchor.inner_text(timeout=900))
        title = title or _clean_text(anchor.inner_text(timeout=900)).split("\n", 1)[0]
        if not title:
            continue
        seen_ids.add(job_id)
        cards.append(
            {
                "url": url,
                "native_source_id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "snippet": card_text[:1000],
                "query": query,
            }
        )
        if len(cards) >= max_results:
            break
    return cards


def _detail_description(page: Any, url: str, *, timeout_ms: int) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(700)
        body = _clean_text(page.locator("body").inner_text(timeout=timeout_ms))
        if access_block_reason(page.url, body, cards=0):
            return ""
        for selector in (
            ".show-more-less-html__markup",
            ".description__text",
            ".jobs-description__content",
        ):
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    text = _clean_text(locator.first.inner_text(timeout=1200))
                    if text:
                        return text[:6000]
            except Exception:  # noqa: S112
                continue
        return body[:6000]
    except Exception:
        return ""


def _launch_context(playwright: Any, source_config: dict[str, Any]) -> Any:
    browser_config = source_config.get("browser") or {}
    if not isinstance(browser_config, dict):
        browser_config = {}
    channel = (
        str(
            source_config.get("browser_channel")
            or browser_config.get("channel")
            or "chrome"
        )
        .strip()
        .lower()
    )
    profile_value = (
        os.environ.get("LINKEDIN_JOBS_PROFILE_DIR")
        or source_config.get("profile_dir")
        or str(DEFAULT_PROFILE_DIR)
    )
    profile_dir = Path(str(profile_value))
    if not profile_dir.is_absolute():
        profile_dir = JOB_ROOT / profile_dir
    profile_dir.mkdir(parents=True, exist_ok=True)
    headed = bool(source_config.get("headed", False)) or os.environ.get(
        "LINKEDIN_JOBS_HEADED", ""
    ).strip() in {"1", "true", "yes"}
    kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": not headed,
        "locale": "en-GB",
        "viewport": {"width": 1320, "height": 920},
    }
    if channel not in {"", "chromium", "bundled", "playwright"}:
        kwargs["channel"] = channel
    try:
        return playwright.chromium.launch_persistent_context(**kwargs)
    except Exception as exc:
        raise LinkedInScrapeError(
            "Could not open the LinkedIn jobs browser profile. "
            "Close another jobs-browser window or run the "
            "--manual-login command once. "
            f"Details: {type(exc).__name__}"
        ) from exc


def _source_config(config: dict[str, Any]) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get("linkedin") or {}
    return block if isinstance(block, dict) else {}


def discover_linkedin_jobs(config: dict[str, Any]) -> list[Opportunity]:
    """Discover current LinkedIn jobs with a read-only browser session."""

    source_config = _source_config(config)
    queries = _queries(source_config)
    if not queries:
        raise LinkedInScrapeError("No LinkedIn job queries are configured.")
    if sync_playwright is None:
        raise LinkedInScrapeError("Python Playwright is not installed.")

    base_url = str(source_config.get("base_url") or "https://www.linkedin.com")
    location = str(source_config.get("location") or "Vilnius, Lithuania")
    posted_hours = _int_setting(source_config.get("posted_within_hours"), 72)
    max_queries = _int_setting(source_config.get("max_queries"), 6)
    max_per_query = _int_setting(source_config.get("max_results_per_query"), 10)
    max_jobs = _int_setting(source_config.get("max_jobs"), 40)
    pages = _int_setting(source_config.get("pages"), 1)
    max_detail_pages = _int_setting(source_config.get("max_detail_pages"), 8, minimum=0)
    timeout_ms = _int_setting(source_config.get("timeout_ms"), 20_000)
    settle_ms = _int_setting(source_config.get("settle_ms"), 1_000, minimum=0)

    cards: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        context = _launch_context(playwright, source_config)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            for query in queries[:max_queries]:
                query_cards: list[dict[str, str]] = []
                for page_number in range(pages):
                    url = build_search_url(
                        base_url=base_url,
                        keywords=query,
                        location=location,
                        posted_within_hours=posted_hours,
                        page_number=page_number,
                    )
                    try:
                        page.goto(
                            url, wait_until="domcontentloaded", timeout=timeout_ms
                        )
                        page.wait_for_timeout(settle_ms)
                        body = _clean_text(
                            page.locator("body").inner_text(timeout=timeout_ms)
                        )
                    except (PlaywrightTimeoutError, TimeoutError) as exc:
                        raise LinkedInScrapeError(
                            f"LinkedIn jobs page timed out for query {query!r}."
                        ) from exc
                    anchors_count = page.locator("a[href*='/jobs/view/']").count()
                    blocked = access_block_reason(page.url, body, cards=anchors_count)
                    if blocked:
                        raise LinkedInScrapeError(blocked)
                    if anchors_count == 0:
                        if any(
                            marker in body.casefold() for marker in NO_RESULTS_MARKERS
                        ):
                            break
                        raise LinkedInScrapeError(
                            "linkedin_selector_empty: no job cards were found"
                        )
                    query_cards.extend(
                        extract_job_cards(
                            page,
                            query=query,
                            max_results=max_per_query,
                        )
                    )
                    if len(query_cards) >= max_per_query:
                        break
                cards.extend(query_cards[:max_per_query])
                if len(cards) >= max_jobs:
                    break

            unique_cards: list[dict[str, str]] = []
            seen_ids: set[str] = set()
            for card in cards:
                job_id = card["native_source_id"]
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                unique_cards.append(card)
                if len(unique_cards) >= max_jobs:
                    break

            details_by_id: dict[str, str] = {}
            for card in unique_cards[:max_detail_pages]:
                detail = _detail_description(page, card["url"], timeout_ms=timeout_ms)
                if detail:
                    details_by_id[card["native_source_id"]] = detail

            now = utc_now_iso()
            opportunities: list[Opportunity] = []
            for card in unique_cards:
                description = (
                    details_by_id.get(card["native_source_id"]) or card["snippet"]
                )
                evidence = OpportunityEvidence(
                    source_facts=[
                        "linkedin:browser_jobs_search",
                        f"linkedin:query:{card['query']}",
                        f"linkedin:job_id:{card['native_source_id']}",
                    ],
                    company_facts=[card["company"]] if card["company"] else [],
                    role_facts=[card["title"]],
                    location_facts=[card["location"]] if card["location"] else [],
                    confidence=0.8,
                )
                opportunities.append(
                    Opportunity(
                        source="linkedin",
                        source_kind=OpportunitySourceKind.JOB_BOARD,
                        native_source_id=card["native_source_id"],
                        source_url=card["url"],
                        title=card["title"],
                        company=card["company"],
                        location=card["location"],
                        remote_policy=infer_remote_policy(
                            f"{card['location']} {description}"
                        ),
                        description=description,
                        discovered_at=now,
                        live_status="unknown",
                        live_check_method="linkedin_search_page",
                        live_check_note="requires_public_job_page_check",
                        evidence=evidence,
                    )
                )
            return opportunities
        finally:
            context.close()


def manual_login(config: dict[str, Any]) -> None:
    """Open the isolated jobs profile and wait for a human to sign in."""

    if sync_playwright is None:
        raise LinkedInScrapeError("Python Playwright is not installed.")
    source_config = dict(_source_config(config))
    source_config["headed"] = True
    base_url = str(source_config.get("base_url") or "https://www.linkedin.com")
    timeout_ms = _int_setting(source_config.get("timeout_ms"), 20_000)
    with sync_playwright() as playwright:
        context = _launch_context(playwright, source_config)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            page.goto(
                f"{base_url.rstrip('/')}/login",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            print(
                "LinkedIn jobs profile is open. Sign in manually, then press Enter "
                "in this terminal to save the session.",
                file=sys.stderr,
            )
            try:
                input()
            except EOFError as exc:
                raise LinkedInScrapeError(
                    "Manual login requires an interactive terminal."
                ) from exc
        finally:
            context.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only LinkedIn jobs scraper")
    parser.add_argument(
        "--config",
        type=Path,
        default=project_path("config", "opportunities.example.yaml"),
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Open the isolated headed profile and wait for a human sign-in.",
    )
    args = parser.parse_args(argv)
    try:
        import yaml

        config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
        if args.manual_login:
            manual_login(config)
            return 0
        rows = discover_linkedin_jobs(config)
        print(
            json.dumps(
                [row.to_json_dict() for row in rows], ensure_ascii=False, indent=2
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
