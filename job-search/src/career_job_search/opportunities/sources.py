"""Local-first opportunity source adapters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.request import Request, urlopen

from career_job_search.cvs.matching import JOB_ROOT, parse_job_file
from career_job_search.integrations.linkedin.opportunities import (
    discover_linkedin_jobs,
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

DEFAULT_INBOX_JOBS = JOB_ROOT / "inbox" / "jobs"
DEFAULT_FETCH_TIMEOUT_SECONDS = 20


@dataclass
class SourceResult:
    source: str
    status: str
    snapshot_type: str
    item_count: int
    duration_ms: int
    complete: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "snapshot_type": self.snapshot_type,
            "item_count": self.item_count,
            "duration_ms": self.duration_ms,
            "complete": self.complete,
            "error": self.error,
        }


@dataclass
class DiscoveryBatch:
    opportunities: list[Opportunity] = field(default_factory=list)
    source_results: list[SourceResult] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return any(result.status == "failed" for result in self.source_results)


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def fetch_json(url: str, *, timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "career-job-search-opportunity-scout/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def normalize_ats_posting(
    provider: str,
    payload: dict[str, Any],
    *,
    company: str = "",
    source_url: str = "",
    source_name: str = "",
) -> Opportunity:
    name = provider.strip().lower()
    title = ""
    location = ""
    url = source_url
    description = ""
    ats_id = ""

    if name == "greenhouse":
        title = str(payload.get("title") or "")
        loc = payload.get("location") or {}
        location = str(loc.get("name") if isinstance(loc, dict) else loc or "")
        url = str(payload.get("absolute_url") or url)
        description = str(payload.get("content") or "")
        ats_id = str(payload.get("id") or "")
    elif name == "lever":
        title = str(payload.get("text") or payload.get("title") or "")
        categories = payload.get("categories") or {}
        location = str(
            categories.get("location") if isinstance(categories, dict) else ""
        )
        url = str(payload.get("hostedUrl") or payload.get("applyUrl") or url)
        description = str(
            payload.get("descriptionPlain") or payload.get("description") or ""
        )
        ats_id = str(payload.get("id") or "")
    elif name == "ashby":
        title = str(payload.get("title") or "")
        loc = payload.get("location") or ""
        if isinstance(loc, dict):
            location = str(
                loc.get("name") or loc.get("location") or loc.get("city") or ""
            )
        else:
            location = str(loc)
        url = str(payload.get("jobUrl") or payload.get("applyUrl") or url)
        description = str(
            payload.get("descriptionPlain") or payload.get("description") or ""
        )
        ats_id = str(payload.get("id") or payload.get("jobId") or "")
    elif name == "smartrecruiters":
        title = str(payload.get("name") or payload.get("title") or "")
        loc = payload.get("location") or {}
        if isinstance(loc, dict):
            location = str(
                loc.get("city") or loc.get("name") or loc.get("country") or ""
            )
        else:
            location = str(loc or "")
        ref = payload.get("ref") or {}
        url = str(
            payload.get("url")
            or payload.get("applyUrl")
            or (ref.get("jobAd") if isinstance(ref, dict) else "")
            or url
        )
        description = str(payload.get("jobAd") or payload.get("description") or "")
        ats_id = str(payload.get("id") or "")
    else:
        raise ValueError(f"Unsupported ATS provider: {provider}")

    evidence = OpportunityEvidence(
        source_facts=[f"ats:{name}", f"ats_id:{ats_id}" if ats_id else ""],
        company_facts=[company] if company else [],
        role_facts=[title] if title else [],
        location_facts=[location] if location else [],
        confidence=0.7,
    )
    evidence.source_facts = [item for item in evidence.source_facts if item]
    return Opportunity(
        source=source_name or name,
        source_kind=OpportunitySourceKind.ATS,
        native_source_id=ats_id,
        source_url=url,
        title=title,
        company=company,
        location=location,
        remote_policy=infer_remote_policy(f"{title} {location} {description}"),
        description=description,
        evidence=evidence,
    )


def _provider_slug(config: dict[str, Any], *names: str) -> str:
    for name in names:
        value = str(config.get(name) or "").strip()
        if value:
            return value
    return ""


def _provider_source_name(provider: str, slug: str) -> str:
    return f"{provider}:{slug}" if slug else provider


def _payload_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def discover_live_ats_provider(
    provider_config: dict[str, Any],
    *,
    timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> list[Opportunity]:
    provider = str(provider_config.get("provider") or "").strip().lower()
    company = str(provider_config.get("company") or "").strip()
    if not provider or not _enabled(provider_config, default=True):
        return []

    if provider == "greenhouse":
        slug = _provider_slug(provider_config, "board_token", "company_slug")
        if not slug:
            return []
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        rows = _payload_rows(fetch_json(url, timeout=timeout), "jobs")
    elif provider == "lever":
        slug = _provider_slug(provider_config, "company_slug", "board_token")
        if not slug:
            return []
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        rows = _payload_rows(fetch_json(url, timeout=timeout), "postings", "jobs")
    elif provider == "ashby":
        slug = _provider_slug(provider_config, "job_board_name", "company_slug")
        if not slug:
            return []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        rows = _payload_rows(fetch_json(url, timeout=timeout), "jobs")
    elif provider == "smartrecruiters":
        slug = _provider_slug(provider_config, "company_identifier", "company_slug")
        if not slug:
            return []
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
        rows = _payload_rows(
            fetch_json(url, timeout=timeout), "content", "jobs", "postings"
        )
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
        except Exception:
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
