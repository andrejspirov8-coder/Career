"""Per-portal feed providers and fetch helpers for opportunity discovery.

The public ``discover_*`` callables wired into :data:`SOURCE_ADAPTERS` and
re-exported from the ``sources`` package. Kept separate from the registry
orchestration so the package ``__init__`` stays under the module-size bound.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError

from career_job_search.cvs.matching import JOB_ROOT, parse_job_file
from career_job_search.opportunities.ats_normalization import (
    _payload_rows,
    _provider_slug,
    _provider_source_name,
    normalize_ats_posting,
)
from career_job_search.opportunities.company_careers_source import (
    discover_official_company_careers_source,
)
from career_job_search.opportunities.cvbankas_source import (
    discover_cvbankas_public_search_source,
)
from career_job_search.opportunities.cvmarket_source import (
    discover_cvmarket_rss_source,
)
from career_job_search.opportunities.cvonline_source import (
    discover_cvonline_public_search_source,
)
from career_job_search.opportunities.eligibility import classify_location_eligibility
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
    OpportunityStatus,
)
from career_job_search.opportunities.normalization import infer_remote_policy
from career_job_search.opportunities.sources.base import SourceDiscovery
from career_job_search.opportunities.uzt_source import (
    discover_uzt_open_data_source,
)
from career_job_search.opportunities.workinlithuania_source import (
    discover_workinlithuania_public_search_source,
)

logger = logging.getLogger(__name__)

# Retry configuration for external API calls.
# ATS providers (Greenhouse, Lever, Ashby, SmartRecruiters) throttle
# aggressively; transient 5xx failures should not crash the entire batch.
MAX_ATS_RETRIES = 3
ATS_RETRY_BASE_DELAY_S = 1.0
ATS_RETRY_MAX_DELAY_S = 8.0
FETCH_RETRY_COUNT = 3
FETCH_RETRY_BASE_DELAY_S = 0.5
FETCH_RETRY_MAX_DELAY_S = 4.0

DEFAULT_INBOX_JOBS = JOB_ROOT / "inbox" / "jobs"
DEFAULT_FETCH_TIMEOUT_SECONDS = 20


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _retry_with_backoff(
    fn,
    *,
    max_retries: int = FETCH_RETRY_COUNT,
    base_delay: float = FETCH_RETRY_BASE_DELAY_S,
    max_delay: float = FETCH_RETRY_MAX_DELAY_S,
) -> Any:
    """Call *fn* with exponential backoff on transient network failures.

    Retries on ``HTTPError`` (5xx), ``URLError``, and ``TimeoutError``.
    Constant backoff capped at *max_delay*.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            sleep(delay)
    raise last_exc  # type: ignore[return-value]


def fetch_json(url: str, *, timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS) -> Any:
    """Fetch and parse JSON from *url* with retry via httpx (sync)."""
    from career_job_search.core.http_client import fetch_text_sync

    text = fetch_text_sync(
        url,
        max_retries=3,
        base_delay=1.0,
        timeout=timeout,
        headers={
            "Accept": "application/json",
            "User-Agent": "career-job-search-opportunity-scout/1.0",
        },
    )
    return json.loads(text)


def fetch_json_limited(
    url: str,
    *,
    timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS,
    rate_limit_seconds: float = 0.0,
    _last_call: list[float] = [0.0],  # noqa: B006 — mutable default, tracks last call time
) -> Any:
    """Rate-limited wrapper around ``fetch_json``.

    Ensures at least *rate_limit_seconds* elapse between requests.
    """
    if rate_limit_seconds > 0:
        now = time.time()
        elapsed = now - _last_call[0]
        if elapsed < rate_limit_seconds:
            wait = rate_limit_seconds - elapsed
            logger.debug("Rate limiting: sleeping %.2fs for %s", wait, url)
            time.sleep(wait)
        _last_call[0] = time.time()
    return fetch_json(url, timeout=timeout)


def fetch_text(url: str, *, timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS) -> str:
    """Fetch text from *url* with retry via httpx (sync)."""
    from career_job_search.core.http_client import fetch_text_sync

    return fetch_text_sync(
        url,
        max_retries=3,
        base_delay=1.0,
        timeout=timeout,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/rss+xml",
            "User-Agent": "career-job-search-opportunity-scout/1.0",
        },
    )


def fetch_text_limited(
    url: str,
    *,
    timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS,
    rate_limit_seconds: float = 0.0,
    _last_call: list[float] = [0.0],  # noqa: B006 — mutable default, tracks last call time
) -> str:
    """Rate-limited wrapper around ``fetch_text``.

    Ensures at least *rate_limit_seconds* elapse between requests.
    The internal `_last_call` list persists state across calls.
    """
    if rate_limit_seconds > 0:
        now = time.time()
        elapsed = now - _last_call[0]
        if elapsed < rate_limit_seconds:
            wait = rate_limit_seconds - elapsed
            logger.debug("Rate limiting: sleeping %.2fs for %s", wait, url)
            time.sleep(wait)
        _last_call[0] = time.time()
    return fetch_text(url, timeout=timeout)


def _rate_limited_fetcher(
    config: dict[str, Any],
    source_key: str,
    *,
    use_json: bool = False,
) -> tuple[Callable[..., str], float]:
    """Return a rate-limited fetcher bound to a source config.

    Returns ``(fetcher, rate_limit_seconds)`` where *fetcher* is either
    ``fetch_json_limited`` or ``fetch_text_limited`` with the configured
    delay baked in.
    """
    block = _source_cfg(config, source_key)
    rate = float(block.get("rate_limit_seconds") or 0.0)
    timeout = int(block.get("network_timeout_seconds") or DEFAULT_FETCH_TIMEOUT_SECONDS)

    if use_json:

        def _json_limited(url: str, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            return fetch_json_limited(url, timeout=timeout, rate_limit_seconds=rate)

        return _json_limited, rate
    else:

        def _text_limited(url: str, **kwargs: Any) -> str:  # type: ignore[no-untyped-def]
            return fetch_text_limited(url, timeout=timeout, rate_limit_seconds=rate)

        return _text_limited, rate


def discover_cvmarket_rss(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> SourceDiscovery:
    fetcher, _ = _rate_limited_fetcher(config, "cvmarket_rss")
    return discover_cvmarket_rss_source(config, fetcher=fetcher, now=now)


def discover_uzt_open_data(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> SourceDiscovery:
    fetcher, _ = _rate_limited_fetcher(config, "uzt", use_json=True)
    live_fetcher, _ = _rate_limited_fetcher(config, "uzt", use_json=False)
    return discover_uzt_open_data_source(
        config,
        fetcher=fetcher,
        live_fetcher=live_fetcher,
        now=now,
    )


def discover_cvonline_public_search(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> SourceDiscovery:
    fetcher, _ = _rate_limited_fetcher(config, "cvonline_public_search")
    return discover_cvonline_public_search_source(
        config,
        fetcher=fetcher,
        now=now,
    )


def discover_workinlithuania_public_search(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> SourceDiscovery:
    fetcher, _ = _rate_limited_fetcher(
        config, "workinlithuania_public_search", use_json=True
    )
    return discover_workinlithuania_public_search_source(
        config,
        fetcher=fetcher,
        now=now,
    )


def discover_cvbankas_public_search(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> SourceDiscovery:
    fetcher, _ = _rate_limited_fetcher(config, "cvbankas_public_search")
    return discover_cvbankas_public_search_source(
        config,
        fetcher=fetcher,
        now=now,
    )


def discover_official_company_careers(
    config: dict[str, Any],
    company_config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> SourceDiscovery:
    return discover_official_company_careers_source(
        config,
        company_config,
        fetcher=fetch_text,
        now=now,
    )


def infer_location(parsed: dict[str, Any]) -> str:
    text = " ".join(
        str(parsed.get(key) or "") for key in ("title", "company", "body", "source")
    ).lower()
    if "vilnius" in text:
        return "Vilnius"
    if "lithuania" in text or "lietuva" in text:
        return "Lithuania"
    if "baltic" in text or "baltics" in text:
        return "Baltics"
    if "remote" in text:
        return "Remote"
    return ""


def opportunity_from_job_file(path: Path) -> Opportunity:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_job_file(raw, job_file_path=str(path.resolve()))
    source = str(parsed.get("source") or "manual_inbox") or "manual_inbox"
    body = str(parsed.get("body") or "")
    title = str(parsed.get("title") or "")
    company = str(parsed.get("company") or "")
    source_url = str(parsed.get("url") or "")
    evidence = OpportunityEvidence(
        source_facts=[f"inbox:{path.name}"],
        company_facts=[company] if company else [],
        role_facts=[title] if title else [],
        location_facts=[infer_location(parsed)] if infer_location(parsed) else [],
        confidence=0.75,
    )
    return Opportunity(
        source=source,
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        source_url=source_url,
        title=title,
        company=company,
        location=infer_location(parsed),
        remote_policy=infer_remote_policy(body),
        description=body,
        evidence=evidence,
    )


def discover_inbox_opportunities(config: dict[str, Any]) -> list[Opportunity]:
    block = _source_cfg(config, "inbox")
    if not _enabled(block, default=True):
        return []
    inbox = Path(str(block.get("path") or DEFAULT_INBOX_JOBS))
    if not inbox.exists():
        return []
    exclude_patterns = [
        str(item).lower()
        for item in block.get("exclude_name_patterns", ["smoke", "test"])
        if str(item).strip()
    ]
    return [
        opportunity_from_job_file(path)
        for path in sorted(inbox.glob("*.job.txt"))
        if not _is_excluded_inbox_job(path, exclude_patterns)
    ]


def _is_excluded_inbox_job(path: Path, exclude_patterns: list[str]) -> bool:
    name = path.name.lower()
    if name.startswith("."):
        return True
    return any(pattern in name for pattern in exclude_patterns)


def discover_live_ats_provider(
    provider_config: dict[str, Any],
    *,
    timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> list[Opportunity]:
    provider = str(provider_config.get("provider") or "").strip().lower()
    company = str(provider_config.get("company") or "").strip()
    if not provider or not _enabled(provider_config, default=True):
        return []

    def _fetch_with_retry(url: str) -> Any:
        return _retry_with_backoff(
            lambda: fetch_json(url, timeout=timeout),
            max_retries=MAX_ATS_RETRIES,
            base_delay=ATS_RETRY_BASE_DELAY_S,
            max_delay=ATS_RETRY_MAX_DELAY_S,
        )

    if provider == "greenhouse":
        slug = _provider_slug(provider_config, "board_token", "company_slug")
        if not slug:
            return []
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        rows = _payload_rows(_fetch_with_retry(url), "jobs")
    elif provider == "lever":
        slug = _provider_slug(provider_config, "company_slug", "board_token")
        if not slug:
            return []
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        rows = _payload_rows(_fetch_with_retry(url), "postings", "jobs")
    elif provider == "ashby":
        slug = _provider_slug(provider_config, "job_board_name", "company_slug")
        if not slug:
            return []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        rows = _payload_rows(_fetch_with_retry(url), "jobs")
    elif provider == "smartrecruiters":
        slug = _provider_slug(provider_config, "company_identifier", "company_slug")
        if not slug:
            return []
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
        rows = _payload_rows(_fetch_with_retry(url), "content", "jobs", "postings")
    else:
        return []

    source_name = _provider_source_name(provider, slug)
    normalized = [
        normalize_ats_posting(
            provider,
            row,
            company=company,
            source_name=source_name,
        )
        for row in rows
    ]
    eligible_rows = [
        _annotate_location(row)
        for row in normalized
        if classify_location_eligibility(row).eligibility != "ineligible"
    ]
    max_posts = int(provider_config.get("max_posts") or len(eligible_rows) or 0)
    return eligible_rows[:max_posts]


def discover_ats_opportunities(config: dict[str, Any]) -> list[Opportunity]:
    block = _source_cfg(config, "ats")
    if not _enabled(block, default=False):
        return []
    rows: list[Opportunity] = []
    for fixture in block.get("fixtures") or []:
        if not isinstance(fixture, dict):
            continue
        provider = str(fixture.get("provider") or "")
        company = str(fixture.get("company") or "")
        path = Path(str(fixture.get("path") or ""))
        if not provider or not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        postings = data if isinstance(data, list) else data.get("jobs") or []
        for item in postings:
            if isinstance(item, dict):
                rows.append(normalize_ats_posting(provider, item, company=company))
    timeout = int(block.get("network_timeout_seconds") or DEFAULT_FETCH_TIMEOUT_SECONDS)
    for provider_config in block.get("providers") or []:
        if not isinstance(provider_config, dict):
            continue
        try:
            rows.extend(discover_live_ats_provider(provider_config, timeout=timeout))
        except Exception:  # noqa: S112
            continue
    return rows


def discover_company_watchlist(config: dict[str, Any]) -> list[Opportunity]:
    block = _source_cfg(config, "company_watchlist")
    if not _enabled(block, default=False):
        return []
    rows: list[Opportunity] = []
    for company in block.get("companies") or []:
        if not isinstance(company, dict):
            continue
        name = str(company.get("name") or "")
        careers_url = str(company.get("careers_url") or "")
        if not name or not careers_url:
            continue
        rows.append(
            Opportunity(
                source="company_watchlist",
                source_kind=OpportunitySourceKind.COMPANY_SITE,
                source_url=careers_url,
                title="Company watchlist",
                company=name,
                description=f"Watch careers page for roles at {name}.",
                status=OpportunityStatus.SKIPPED,
                evidence=OpportunityEvidence(
                    source_facts=[careers_url],
                    company_facts=[name],
                    risk_flags=["watchlist_only"],
                    confidence=0.35,
                ),
            )
        )
    return rows


def discover_link_list(
    config: dict[str, Any], name: str, kind: OpportunitySourceKind
) -> list[Opportunity]:
    block = _source_cfg(config, name)
    if not _enabled(block, default=False):
        return []
    rows: list[Opportunity] = []
    for item in block.get("links") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Manual review link")
        company = str(item.get("company") or "")
        url = str(item.get("url") or "")
        rows.append(
            Opportunity(
                source=name,
                source_kind=kind,
                source_url=url,
                title=title,
                company=company,
                location=str(item.get("location") or ""),
                description=str(item.get("description") or title),
                evidence=OpportunityEvidence(
                    source_facts=[url] if url else [],
                    role_facts=[title],
                    risk_flags=["link_review_required"],
                    confidence=0.4,
                ),
            )
        )
    return rows


def _annotate_location(opportunity: Opportunity) -> Opportunity:
    result = classify_location_eligibility(opportunity)
    opportunity.location_eligibility = result.eligibility
    opportunity.eligibility_reason = result.reason
    if not opportunity.remote_policy and result.work_mode != "unknown":
        opportunity.remote_policy = result.work_mode
    return opportunity
