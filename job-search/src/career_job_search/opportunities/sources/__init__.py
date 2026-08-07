"""Local-first opportunity source discovery: registry + shared adapters.

The ``sources`` package exposes the public discovery surface (``fetch_json``,
``discover_opportunities_with_results``, the per-portal ``discover_*``
functions) and dispatches through a central registry (:data:`SOURCE_ADAPTERS`).
New job portals are added by defining a ``discover_*`` callable and registering
a :class:`~career_job_search.opportunities.sources.registry.RegistrySource`
entry -- no orchestrator edits required.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from career_job_search.integrations.linkedin.opportunities import (
    discover_linkedin_jobs,
)
from career_job_search.opportunities.ats_normalization import (
    _provider_slug,
    _provider_source_name,
    normalize_ats_posting,
)
from career_job_search.opportunities.eligibility import classify_location_eligibility
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunitySourceKind,
    company_title_location_key,
    normalise_url,
)
from career_job_search.opportunities.sources.base import (
    DiscoveryBatch,
    SourceAdapter,
    SourceDiscovery,
    SourceResult,
)
from career_job_search.opportunities.sources.providers import (
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    _annotate_location,
    _enabled,
    _source_cfg,
    discover_ats_opportunities,
    discover_company_watchlist,
    discover_cvbankas_public_search,
    discover_cvmarket_rss,
    discover_cvonline_public_search,
    discover_inbox_opportunities,
    discover_link_list,
    discover_live_ats_provider,
    discover_official_company_careers,
    discover_uzt_open_data,
    discover_workinlithuania_public_search,
    fetch_json,
    fetch_json_limited,
    fetch_text,
    fetch_text_limited,
)
from career_job_search.opportunities.sources.registry import (
    SOURCE_ADAPTERS,
    RegistrySource,
)


def _discover_inbox(
    config: dict[str, Any], *, now: datetime | None = None
) -> SourceDiscovery:
    return SourceDiscovery(opportunities=discover_inbox_opportunities(config))


def _discover_watchlist(
    config: dict[str, Any], *, now: datetime | None = None
) -> SourceDiscovery:
    return SourceDiscovery(
        opportunities=discover_company_watchlist(config), status="monitor_only"
    )


def _discover_linkedin(
    config: dict[str, Any], *, now: datetime | None = None
) -> SourceDiscovery:
    return SourceDiscovery(opportunities=discover_linkedin_jobs(config))


def _discover_job_board(
    config: dict[str, Any], *, now: datetime | None = None
) -> SourceDiscovery:
    return SourceDiscovery(
        opportunities=discover_link_list(
            config, "job_board", OpportunitySourceKind.JOB_BOARD
        )
    )


def _discover_web_search(
    config: dict[str, Any], *, now: datetime | None = None
) -> SourceDiscovery:
    return SourceDiscovery(
        opportunities=discover_link_list(
            config, "web_search", OpportunitySourceKind.WEB_SEARCH
        )
    )


def _discover_ats_each(
    config: dict[str, Any], *, now: datetime | None = None
) -> list[tuple[str, SourceDiscovery | BaseException]]:
    """Per-provider ATS discoveries plus any configured fixture batch."""
    block = _source_cfg(config, "ats")
    results: list[tuple[str, SourceDiscovery | BaseException]] = []
    timeout = int(block.get("network_timeout_seconds") or DEFAULT_FETCH_TIMEOUT_SECONDS)
    for provider_config in block.get("providers") or []:
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
        source_name = _provider_source_name(provider, slug)
        try:
            rows = discover_live_ats_provider(provider_config, timeout=timeout)
        except Exception as exc:
            results.append((source_name, exc))
            continue
        results.append(
            (
                source_name,
                SourceDiscovery(
                    opportunities=rows,
                    complete=not bool(provider_config.get("max_posts")),
                ),
            )
        )
    fixture_rows = _discover_ats_fixture_opportunities(block)
    if block.get("fixtures"):
        results.append(
            ("ats:fixtures", SourceDiscovery(opportunities=fixture_rows, complete=True))
        )
    return results


def _discover_company_careers_each(
    config: dict[str, Any], *, now: datetime | None = None
) -> list[tuple[str, SourceDiscovery | BaseException]]:
    """Per-company official careers-page discoveries."""
    block = _source_cfg(config, "official_company_careers")
    results: list[tuple[str, SourceDiscovery | BaseException]] = []
    for company_config in block.get("companies") or []:
        if not isinstance(company_config, dict) or not _enabled(
            company_config, default=True
        ):
            continue
        provider = str(company_config.get("provider") or "").strip().casefold()
        try:
            discovery = discover_official_company_careers(config, company_config)
        except Exception as exc:
            results.append((f"company_careers:{provider}", exc))
            continue
        results.append((f"company_careers:{provider}", discovery))
    return results


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


def _run_single_discovery(
    adapter: RegistrySource,
    config: dict[str, Any],
    *,
    now: datetime | None,
) -> SourceDiscovery:
    fn = globals().get(adapter.discover_name)
    if fn is None:
        raise ValueError(
            f"Unregistered source discovery function: {adapter.discover_name}"
        )
    return fn(config)


def _run_multi_discovery(
    adapter: RegistrySource,
    config: dict[str, Any],
    *,
    now: datetime | None,
) -> list[tuple[str, SourceDiscovery | BaseException]]:
    fn = globals().get(adapter.discover_name)
    if fn is None:
        raise ValueError(
            f"Unregistered source discovery function: {adapter.discover_name}"
        )
    return fn(config)


def discover_opportunities(config: dict[str, Any]) -> list[Opportunity]:
    return discover_opportunities_with_results(config).opportunities


def discover_opportunities_with_results(
    config: dict[str, Any], *, now: datetime | None = None
) -> DiscoveryBatch:
    batch = DiscoveryBatch()

    for adapter in SOURCE_ADAPTERS:
        if not adapter.enabled(config):
            continue
        if adapter.multi:
            items = _run_multi_discovery(adapter, config, now=now)
            for source_name, item in items:
                if isinstance(item, BaseException):
                    batch.source_results.append(
                        SourceResult(
                            source=source_name,
                            status="failed",
                            snapshot_type=adapter.snapshot_type,
                            item_count=0,
                            duration_ms=0,
                            complete=False,
                            error=_redact_source_error(item),
                        )
                    )
                    continue
                _collect_discovery_source(
                    batch,
                    source=source_name,
                    snapshot_type=adapter.snapshot_type,
                    discover=lambda discovery=item: discovery,
                )
            continue
        _collect_discovery_source(
            batch,
            source=adapter.name,
            snapshot_type=adapter.snapshot_type,
            discover=lambda a=adapter: _run_single_discovery(a, config, now=now),
        )

    batch.opportunities = dedupe_opportunities(batch.opportunities)
    return batch


def _collect_discovery_source(
    batch: DiscoveryBatch,
    *,
    source: str,
    snapshot_type: str,
    discover: Callable[[], SourceDiscovery],
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
    status = getattr(discovery, "status", None) or ("success" if annotated else "empty")
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


# Populate the discovery registry at import time. Imported last to avoid any
# circular reference with the adapter modules above.
import career_job_search.opportunities.sources.adapters as _adapters  # noqa: E402,F401

__all__ = [
    "SOURCE_ADAPTERS",
    "DiscoveryBatch",
    "RegistrySource",
    "SourceAdapter",
    "SourceDiscovery",
    "SourceResult",
    "dedupe_opportunities",
    "discover_ats_opportunities",
    "discover_company_watchlist",
    "discover_cvbankas_public_search",
    "discover_cvmarket_rss",
    "discover_cvonline_public_search",
    "discover_inbox_opportunities",
    "discover_link_list",
    "discover_live_ats_provider",
    "discover_official_company_careers",
    "discover_opportunities",
    "discover_opportunities_with_results",
    "discover_uzt_open_data",
    "discover_workinlithuania_public_search",
    "fetch_json",
    "fetch_json_limited",
    "fetch_text",
    "fetch_text_limited",
]
