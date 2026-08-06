"""Local-first opportunity source adapters."""

from __future__ import annotations

import logging
import time
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter, sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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

from career_job_search.cvs.matching import JOB_ROOT, parse_job_file
from career_job_search.integrations.linkedin.opportunities import (
    discover_linkedin_jobs,
)
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
    company_title_location_key,
    normalise_url,
)
from career_job_search.opportunities.normalization import infer_remote_policy
from career_job_search.opportunities.uzt_source import (
    discover_uzt_open_data_source,
)
from career_job_search.opportunities.workinlithuania_source import (
    discover_workinlithuania_public_search_source,
)

DEFAULT_INBOX_JOBS = JOB_ROOT / "inbox" / "jobs"
DEFAULT_FETCH_TIMEOUT_SECONDS = 20


from career_job_search.opportunities.sources_package.base import (
    DiscoveryBatch,
    SourceDiscovery,
    SourceResult,
)


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
            return fetch_json_limited(
                url, timeout=timeout, rate_limit_seconds=rate
            )
        return _json_limited, rate
    else:
        def _text_limited(url: str, **kwargs: Any) -> str:  # type: ignore[no-untyped-def]
            return fetch_text_limited(
                url, timeout=timeout, rate_limit_seconds=rate
            )
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
    fetcher, _ = _rate_limited_fetcher(config, "workinlithuania_public_search", use_json=True)
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


def discover_opportunities(config: dict[str, Any]) -> list[Opportunity]:
    return discover_opportunities_with_results(config).opportunities


def discover_opportunities_with_results(config: dict[str, Any]) -> DiscoveryBatch:
    batch = DiscoveryBatch()

    inbox = _source_cfg(config, "inbox")
    if _enabled(inbox, default=True):
        _collect_source(
            batch,
            source="inbox",
            snapshot_type="snapshot",
            discover=lambda: discover_inbox_opportunities(config),
        )

    watchlist = _source_cfg(config, "company_watchlist")
    if _enabled(watchlist, default=False):
        _collect_source(
            batch,
            source="company_watchlist",
            snapshot_type="snapshot",
            result_status="monitor_only",
            discover=lambda: discover_company_watchlist(config),
        )

    ats = _source_cfg(config, "ats")
    if _enabled(ats, default=False):
        timeout = int(
            ats.get("network_timeout_seconds") or DEFAULT_FETCH_TIMEOUT_SECONDS
        )
        for provider_config in ats.get("providers") or []:
            if not isinstance(provider_config, dict) or not _enabled(
                provider_config, default=True
            ):
                continue
            provider = str(provider_config.get("provider") or "").strip().lower()
            slug = _provider_slug(
                provider_config,
                "board_token",
                "company_slug",
                "job_board_name",
                "company_identifier",
            )
            _collect_source(
                batch,
                source=_provider_source_name(provider, slug),
                snapshot_type="snapshot",
                complete=not bool(provider_config.get("max_posts")),
                discover=lambda cfg=provider_config: discover_live_ats_provider(
                    cfg, timeout=timeout
                ),
            )
        fixture_rows = _discover_ats_fixture_opportunities(ats)
        if ats.get("fixtures"):
            batch.opportunities.extend(fixture_rows)
            batch.source_results.append(
                SourceResult(
                    source="ats:fixtures",
                    status="success" if fixture_rows else "empty",
                    snapshot_type="snapshot",
                    item_count=len(fixture_rows),
                    duration_ms=0,
                    complete=True,
                )
            )

    linkedin = _source_cfg(config, "linkedin")
    linkedin_mode = str(linkedin.get("mode") or "local_profile").strip().casefold()
    if _enabled(linkedin, default=False) and linkedin_mode not in {
        "connected_chrome",
        "chrome_session",
        "external_browser",
    }:
        _collect_source(
            batch,
            source="linkedin",
            snapshot_type="snapshot",
            discover=lambda: discover_linkedin_jobs(config),
        )

    for name, kind in (
        ("job_board", OpportunitySourceKind.JOB_BOARD),
        ("web_search", OpportunitySourceKind.WEB_SEARCH),
    ):
        block = _source_cfg(config, name)
        if _enabled(block, default=False):
            _collect_source(
                batch,
                source=name,
                snapshot_type="snapshot",
                discover=lambda source_name=name, source_kind=kind: discover_link_list(
                    config, source_name, source_kind
                ),
            )

    cvmarket = _source_cfg(config, "cvmarket_rss")
    if _enabled(cvmarket, default=False):
        _collect_discovery_source(
            batch,
            source="cvmarket",
            snapshot_type="incremental",
            discover=lambda: discover_cvmarket_rss(config),
        )

    cvonline = _source_cfg(config, "cvonline_public_search")
    if _enabled(cvonline, default=False):
        _collect_discovery_source(
            batch,
            source="cvonline",
            snapshot_type="incremental",
            discover=lambda: discover_cvonline_public_search(config),
        )

    cvbankas = _source_cfg(config, "cvbankas_public_search")
    if _enabled(cvbankas, default=False):
        _collect_discovery_source(
            batch,
            source="cvbankas",
            snapshot_type="incremental",
            discover=lambda: discover_cvbankas_public_search(config),
        )

    workinlithuania = _source_cfg(config, "workinlithuania_public_search")
    if _enabled(workinlithuania, default=False):
        _collect_discovery_source(
            batch,
            source="workinlithuania",
            snapshot_type="snapshot",
            discover=lambda: discover_workinlithuania_public_search(config),
        )

    uzt = _source_cfg(config, "uzt_open_data")
    if _enabled(uzt, default=False):
        _collect_discovery_source(
            batch,
            source="uzt_open_data",
            snapshot_type="incremental",
            discover=lambda: discover_uzt_open_data(config),
        )

    company_careers = _source_cfg(config, "official_company_careers")
    if _enabled(company_careers, default=False):
        for company_config in company_careers.get("companies") or []:
            if not isinstance(company_config, dict) or not _enabled(
                company_config, default=True
            ):
                continue
            provider = str(company_config.get("provider") or "").strip().casefold()
            _collect_discovery_source(
                batch,
                source=f"company_careers:{provider}",
                snapshot_type="snapshot",
                discover=lambda cfg=company_config: (
                    discover_official_company_careers(config, cfg)
                ),
            )

    batch.opportunities = dedupe_opportunities(batch.opportunities)
    return batch


def _discover_ats_fixture_opportunities(block: dict[str, Any]) -> list[Opportunity]:
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
                row = normalize_ats_posting(provider, item, company=company)
                if classify_location_eligibility(row).eligibility != "ineligible":
                    rows.append(_annotate_location(row))
    return rows


def _collect_source(
    batch: DiscoveryBatch,
    *,
    source: str,
    snapshot_type: str,
    discover: Any,
    complete: bool = True,
    result_status: str | None = None,
) -> None:
    started = perf_counter()
    try:
        rows = discover()
    except Exception as exc:
        batch.source_results.append(
            SourceResult(
                source=source,
                status="failed",
                snapshot_type=snapshot_type,
                item_count=0,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
                complete=False,
                error=_redact_source_error(exc),
            )
        )
        return
    annotated = [_annotate_location(row) for row in rows]
    batch.opportunities.extend(annotated)
    batch.source_results.append(
        SourceResult(
            source=source,
            status=result_status or ("success" if annotated else "empty"),
            snapshot_type=snapshot_type,
            item_count=len(annotated),
            duration_ms=max(0, int((perf_counter() - started) * 1000)),
            complete=complete,
        )
    )


def _collect_discovery_source(
    batch: DiscoveryBatch,
    *,
    source: str,
    snapshot_type: str,
    discover: Any,
) -> None:
    started = perf_counter()
    try:
        discovery = discover()
    except Exception as exc:
        batch.source_results.append(
            SourceResult(
                source=source,
                status="failed",
                snapshot_type=snapshot_type,
                item_count=0,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
                complete=False,
                error=_redact_source_error(exc),
            )
        )
        return
    rows = list(getattr(discovery, "opportunities", []))
    annotated = [_annotate_location(row) for row in rows]
    batch.opportunities.extend(annotated)
    status = getattr(discovery, "status", None) or (
        "success" if annotated else "empty"
    )
    batch.source_results.append(
        SourceResult(
            source=source,
            status=status,
            snapshot_type=snapshot_type,
            item_count=len(annotated),
            duration_ms=max(0, int((perf_counter() - started) * 1000)),
            complete=bool(getattr(discovery, "complete", True)),
        )
    )


def _annotate_location(opportunity: Opportunity) -> Opportunity:
    result = classify_location_eligibility(opportunity)
    opportunity.location_eligibility = result.eligibility
    opportunity.eligibility_reason = result.reason
    if not opportunity.remote_policy and result.work_mode != "unknown":
        opportunity.remote_policy = result.work_mode
    return opportunity


def _redact_source_error(error: object) -> str:
    text = " ".join(str(error or "").split())
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret)\s*[:=]\s*([^\s,;]+)",
        r"\1=[redacted]",
        text,
    )
    return text[:240]


def _dedupe_keys(opportunity: Opportunity) -> list[str]:
    keys: list[str] = []
    url = normalise_url(opportunity.source_url)
    if url:
        keys.append(f"url:{url}")
    ctl = company_title_location_key(
        opportunity.company, opportunity.title, opportunity.location
    )
    if ctl != "ctl:":
        keys.append(ctl)
    if not keys:
        keys.append(opportunity.dedupe_key)
    return keys


def dedupe_opportunities(rows: list[Opportunity]) -> list[Opportunity]:
    unique: list[Opportunity] = []
    key_to_index: dict[str, int] = {}
    for row in rows:
        keys = _dedupe_keys(row)
        matched_index = next(
            (key_to_index[key] for key in keys if key in key_to_index), None
        )
        if matched_index is None:
            key_to_index.update({key: len(unique) for key in keys})
            row.duplicate_cluster_id = row.duplicate_cluster_id or row.opportunity_id
            unique.append(row)
            continue
        existing = unique[matched_index]
        flags = list(dict.fromkeys([*existing.evidence.risk_flags, "duplicate"]))
        existing.evidence.risk_flags = flags
        existing.duplicate_cluster_id = (
            existing.duplicate_cluster_id or existing.opportunity_id
        )
        existing.evidence.source_facts = list(
            dict.fromkeys([*existing.evidence.source_facts, *row.evidence.source_facts])
        )
        for key in keys:
            key_to_index[key] = matched_index
    return unique
