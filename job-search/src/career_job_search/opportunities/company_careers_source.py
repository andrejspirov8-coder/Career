"""Official public career-page opportunity adapters for priority companies."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
    OpportunityStatus,
)
from career_job_search.opportunities.normalization import infer_remote_policy
from career_job_search.opportunities.sources.base import SourceDiscovery

DEFAULT_FETCH_TIMEOUT_SECONDS = 30
DEFAULT_MAX_PAGE_CHARS = 12_000_000
DEFAULT_MAX_ROWS_PER_COMPANY = 400
MAX_COMPANIES = 5
MAX_PUBLIC_DESCRIPTION_CHARS = 6000

_PROVIDER_PATHS = {
    "bolt": ("bolt.eu", "/en/careers/positions"),
    "vinted": ("careers.vinted.com", "/jobs"),
    "wolt": ("careers.wolt.com", "/en/jobs"),
}
_EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}|00\d{1,3})(?:[\s().-]*\d){7,12}(?!\d)",
)
_CONTACT_SECTION_RE = re.compile(
    r"(?i)\b(?:contact\s+person|recruitment\s+contact|"
    r"for\s+questions\s+contact|if\s+you\s+have\s+any\s+questions|"
    r"kontaktinis\s+asmuo|jeigu\s+kyla\s+klausimų|kontaktai)\b",
)
_BOLT_JOB_RE = re.compile(
    r'\{"id":"[0-9a-f-]{36}","header":',
    re.IGNORECASE,
)
_WOLT_JOB_RE = re.compile(r'\{"id":\d+,"internalId":')
_EURO_RANGE_RE = re.compile(
    r"(?i)(?:ranges?\s+from\s+)?"
    r"([\d][\d\s,.]*)\s*€\s*(?:to|[-–—])\s*"
    r"([\d][\d\s,.]*)\s*€",
)


@dataclass
class CompanyCareersSourceDiscovery(SourceDiscovery):
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""


def company_careers_source_name(provider: str) -> str:
    return f"company_careers:{provider.strip().casefold() or 'invalid'}"


def discover_company_watchlist(config: dict[str, Any]) -> list[Opportunity]:
    """Return monitor-only rows for companies without an automatic source."""

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


def discover_official_company_careers_source(
    config: dict[str, Any],
    company_config: dict[str, Any],
    *,
    fetcher: Callable[..., str],
    now: datetime | None = None,
) -> CompanyCareersSourceDiscovery:
    """Read one publisher-rendered job list without opening detail pages."""

    block = _source_cfg(config, "official_company_careers")
    if not _enabled(block, default=False) or not _enabled(
        company_config,
        default=True,
    ):
        return CompanyCareersSourceDiscovery()

    provider = str(company_config.get("provider") or "").strip().casefold()
    company = " ".join(str(company_config.get("company") or "").split())
    if provider not in _PROVIDER_PATHS:
        raise ValueError("Unsupported official company-careers provider.")
    if not company:
        raise ValueError("Official company-careers company is required.")
    listing_url = _validated_listing_url(
        provider,
        str(company_config.get("listing_url") or ""),
    )
    timeout = _bounded_int(
        company_config.get(
            "network_timeout_seconds",
            block.get("network_timeout_seconds", DEFAULT_FETCH_TIMEOUT_SECONDS),
        ),
        "network_timeout_seconds",
        maximum=60,
    )
    max_page_chars = _bounded_int(
        company_config.get(
            "max_page_chars",
            block.get("max_page_chars", DEFAULT_MAX_PAGE_CHARS),
        ),
        "max_page_chars",
        maximum=20_000_000,
    )
    max_rows = _bounded_int(
        company_config.get(
            "max_rows",
            block.get("max_rows_per_company", DEFAULT_MAX_ROWS_PER_COMPANY),
        ),
        "max_rows",
        maximum=500,
    )

    page = fetcher(listing_url, timeout=timeout)
    if len(page) > max_page_chars:
        raise ValueError("Official company careers page exceeded its size cap.")
    rows = _parse_provider_rows(provider, page)
    if not rows:
        raise ValueError("Official company careers page returned no parseable jobs.")

    complete = len(rows) <= max_rows
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    opportunities = [
        opportunity
        for row in rows[:max_rows]
        if (
            opportunity := _row_to_opportunity(
                provider,
                row,
                company=company,
                listing_url=listing_url,
                checked_at=clock,
            )
        )
        is not None
    ]
    note = ""
    if not complete:
        note = (
            f"{company}'s public careers page exceeded the "
            f"{max_rows}-job processing cap."
        )
    return CompanyCareersSourceDiscovery(
        opportunities=_dedupe_opportunities(opportunities),
        complete=complete,
        note=note,
    )


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _bounded_int(value: Any, name: str, *, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}.")
    return parsed


def _validated_listing_url(provider: str, value: str) -> str:
    parsed = urlsplit(value.strip())
    expected_host, path_prefix = _PROVIDER_PATHS[provider]
    host = parsed.netloc.casefold().removeprefix("www.")
    if parsed.scheme.casefold() != "https" or host != expected_host:
        raise ValueError(f"{provider} listing_url must use its official HTTPS host.")
    if not parsed.path.rstrip("/").startswith(path_prefix):
        raise ValueError(f"{provider} listing_url must use its official jobs path.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _parse_provider_rows(provider: str, page: str) -> list[dict[str, Any]]:
    if provider == "vinted":
        return _vinted_rows(page)
    stream = _next_rsc_text(page)
    if provider == "wolt":
        return _embedded_objects(
            stream,
            _WOLT_JOB_RE,
            required_keys={"id", "internalId", "title", "offices"},
        )
    return _embedded_objects(
        stream,
        _BOLT_JOB_RE,
        required_keys={"id", "header", "body"},
    )


def _vinted_rows(page: str) -> list[dict[str, Any]]:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise ValueError("Vinted careers page is missing __NEXT_DATA__.")
    payload = json.loads(match.group(1))
    data_map = (
        (payload.get("props") or {})
        .get("pageProps", {})
        .get("jobs", {})
        .get("dataMap", {})
    )
    if not isinstance(data_map, dict):
        raise ValueError("Vinted careers data map is malformed.")
    english = data_map.get("vinteden")
    if not isinstance(english, dict):
        candidates = [
            value
            for value in data_map.values()
            if isinstance(value, dict) and isinstance(value.get("jobs"), list)
        ]
        english = max(candidates, key=lambda item: len(item["jobs"]), default={})
    jobs = english.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Vinted careers page is missing English jobs.")

    flattened: list[dict[str, Any]] = []
    for raw in jobs:
        if not isinstance(raw, dict):
            continue
        items = raw.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if isinstance(item, dict):
                    merged = {**raw, **item, "items": []}
                    if "location" not in item and (
                        item.get("city") or item.get("country")
                    ):
                        merged["location"] = None
                    flattened.append(merged)
        else:
            flattened.append(raw)
    return _dedupe_rows(flattened)


def _next_rsc_text(page: str) -> str:
    fragments: list[str] = []
    for raw in re.findall(
        r"<script[^>]*>(.*?)</script>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        match = re.fullmatch(
            r"\s*self\.__next_f\.push\((.*)\)\s*",
            raw,
            flags=re.DOTALL,
        )
        if match is None:
            continue
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, list)
            and len(payload) > 1
            and isinstance(payload[1], str)
        ):
            fragments.append(payload[1])
    if not fragments:
        raise ValueError("Official careers page is missing its public job data.")
    return "\n".join(fragments)


def _embedded_objects(
    text: str,
    marker: re.Pattern[str],
    *,
    required_keys: set[str],
) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    rows: list[dict[str, Any]] = []
    for match in marker.finditer(text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and required_keys <= value.keys():
            rows.append(value)
    return _dedupe_rows(rows)


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        native_id = str(row.get("id") or "").strip()
        if native_id:
            by_id.setdefault(native_id, row)
    return list(by_id.values())


def _row_to_opportunity(
    provider: str,
    row: dict[str, Any],
    *,
    company: str,
    listing_url: str,
    checked_at: datetime,
) -> Opportunity | None:
    if provider == "vinted":
        return _vinted_opportunity(
            row,
            company=company,
            listing_url=listing_url,
            checked_at=checked_at,
        )
    if provider == "wolt":
        return _wolt_opportunity(
            row,
            company=company,
            listing_url=listing_url,
            checked_at=checked_at,
        )
    return _bolt_opportunity(
        row,
        company=company,
        listing_url=listing_url,
        checked_at=checked_at,
    )


def _vinted_opportunity(
    row: dict[str, Any],
    *,
    company: str,
    listing_url: str,
    checked_at: datetime,
) -> Opportunity | None:
    native_id = str(row.get("id") or "").strip()
    title = _plain_text(row.get("title"))
    location = _vinted_location(row)
    if not native_id or not title or not _eligible_location(location):
        return None
    description = _safe_public_text(str(row.get("content") or ""))
    department = _names(row.get("departments"))
    if department:
        description = f"Department: {department}. {description}".strip()
    return _opportunity(
        provider="vinted",
        native_id=native_id,
        title=title,
        company=company,
        location=location,
        description=description,
        salary_text="",
        deadline=_iso_date(row.get("application_deadline")),
        source_updated_at=str(row.get("updated_at") or "").strip(),
        source_url=f"https://careers.vinted.com/jobs/j/{native_id}",
        listing_url=listing_url,
        checked_at=checked_at,
        role_facts=[title, department],
    )


def _wolt_opportunity(
    row: dict[str, Any],
    *,
    company: str,
    listing_url: str,
    checked_at: datetime,
) -> Opportunity | None:
    native_id = str(row.get("id") or "").strip()
    title = _plain_text(row.get("title"))
    location = _names(row.get("offices"))
    if not native_id or not title or not _eligible_location(location):
        return None
    department = _names(row.get("departments"))
    employment = _plain_text(row.get("employmentType"))
    description = ". ".join(
        part
        for part in (
            title,
            f"Department: {department}" if department else "",
            f"Employment: {employment}" if employment else "",
            "Summary from Wolt's official public careers search",
        )
        if part
    )
    return _opportunity(
        provider="wolt",
        native_id=native_id,
        title=title,
        company=company,
        location=location,
        description=description,
        salary_text=_wolt_salary(row.get("payRanges")),
        deadline="",
        source_updated_at="",
        source_url=f"https://careers.wolt.com/en/jobs/1/{native_id}",
        listing_url=listing_url,
        checked_at=checked_at,
        role_facts=[title, department],
    )


def _bolt_opportunity(
    row: dict[str, Any],
    *,
    company: str,
    listing_url: str,
    checked_at: datetime,
) -> Opportunity | None:
    header = row.get("header")
    body = row.get("body")
    if not isinstance(header, dict) or not isinstance(body, dict):
        return None
    native_id = str(row.get("id") or "").strip()
    title = _plain_text(header.get("roleTitle"))
    location = _bolt_locations(header.get("locations"))
    if not native_id or not title or not _eligible_location(location):
        return None
    team = _plain_text(header.get("parentTeamTitle"))
    raw_description = str(body.get("description") or "")
    description = _safe_public_text(raw_description)
    if team:
        description = f"Team: {team}. {description}".strip()
    return _opportunity(
        provider="bolt",
        native_id=native_id,
        title=title,
        company=company,
        location=location,
        description=description,
        salary_text=_bolt_salary(raw_description),
        deadline="",
        source_updated_at=_rsc_date(body.get("jobPostedDate")),
        source_url=f"https://bolt.eu/en/careers/positions/{native_id}/",
        listing_url=listing_url,
        checked_at=checked_at,
        role_facts=[title, team],
    )


def _opportunity(
    *,
    provider: str,
    native_id: str,
    title: str,
    company: str,
    location: str,
    description: str,
    salary_text: str,
    deadline: str,
    source_updated_at: str,
    source_url: str,
    listing_url: str,
    checked_at: datetime,
    role_facts: list[str],
) -> Opportunity:
    checked_iso = checked_at.astimezone(UTC).isoformat()
    safe_description = description or f"{title} at {company}."
    return Opportunity(
        source=company_careers_source_name(provider),
        source_kind=OpportunitySourceKind.COMPANY_SITE,
        native_source_id=native_id,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        remote_policy=_remote_policy(location, safe_description),
        description=safe_description[:MAX_PUBLIC_DESCRIPTION_CHARS],
        salary_text=salary_text,
        deadline=deadline,
        source_updated_at=source_updated_at,
        live_status="live",
        live_checked_at=checked_iso,
        live_check_method="official_public_career_search",
        live_check_note="present_in_current_official_careers_search",
        evidence=OpportunityEvidence(
            source_facts=[f"official_careers:{provider}", listing_url],
            company_facts=[company],
            role_facts=[fact for fact in role_facts if fact],
            location_facts=[location],
            risk_flags=["career_search_summary"],
            confidence=0.85,
        ),
    )


def _plain_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or ""
    return " ".join(str(value or "").split())


def _names(value: Any) -> str:
    if not isinstance(value, list):
        return _plain_text(value)
    names = [_plain_text(item) for item in value]
    return "; ".join(name for name in names if name)


def _vinted_location(row: dict[str, Any]) -> str:
    location = _plain_text(row.get("location"))
    if location:
        return location
    city = _plain_text(row.get("city"))
    country = _plain_text(row.get("country"))
    return ", ".join(part for part in (city, country) if part)


def _bolt_locations(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    locations: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        location = ", ".join(
            part
            for part in (
                _plain_text(item.get("city")),
                _plain_text(item.get("country")),
            )
            if part
        )
        if location:
            locations.append(location)
    return "; ".join(dict.fromkeys(locations))


def _eligible_location(value: str) -> bool:
    normalized = value.casefold()
    if "vilnius" in normalized:
        return True
    return "remote" in normalized and any(
        scope in normalized
        for scope in ("lithuania", "lietuva", "europe", "european union", " eu")
    )


def _remote_policy(location: str, description: str) -> str:
    mode = infer_remote_policy(f"{location} {description}")
    if mode == "hybrid" and "vilnius" in location.casefold():
        return "Hybrid in Vilnius"
    if mode == "remote":
        if "lithuan" in location.casefold():
            return "Remote Lithuania"
        return "Remote EU"
    return "Onsite in Vilnius" if "vilnius" in location.casefold() else ""


def _wolt_salary(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    ranges = [item for item in value if isinstance(item, dict)]
    selected = next(
        (
            item
            for item in ranges
            if "lithuania" in str(item.get("title") or "").casefold()
        ),
        ranges[0] if ranges else None,
    )
    if selected is None:
        return ""
    lower = _number_text(selected.get("minAmount"))
    upper = _number_text(selected.get("maxAmount"))
    currency = _plain_text(selected.get("currency"))
    title = _plain_text(selected.get("title")).rstrip(":")
    amount = (
        f"{lower}–{upper}" if lower and upper and lower != upper else lower or upper
    )
    return " · ".join(part for part in (f"{amount} {currency}".strip(), title) if part)


def _bolt_salary(value: str) -> str:
    match = _EURO_RANGE_RE.search(value)
    if match is None:
        return ""
    lower = _number_text(match.group(1).replace(" ", "").replace(",", ""))
    upper = _number_text(match.group(2).replace(" ", "").replace(",", ""))
    if not lower or not upper:
        return ""
    suffix = " gross/month" if "monthly gross" in value.casefold() else ""
    return f"{lower}–{upper} EUR{suffix}"


def _number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    if number.is_integer():
        return f"{number:,.0f}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _iso_date(value: Any) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or "").strip())
    return match.group(1) if match else ""


def _rsc_date(value: Any) -> str:
    return str(value or "").strip().removeprefix("$D")


class _PublicTextParser(HTMLParser):
    _BLOCK_TAGS = frozenset({"br", "div", "li", "p", "section"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        name = tag.casefold()
        if name in {"script", "style"}:
            self._ignored_depth += 1
        elif not self._ignored_depth and name in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and name in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def _safe_public_text(value: str) -> str:
    parser = _PublicTextParser()
    parser.feed(value)
    text = " ".join("".join(parser.parts).split())
    contact_section = _CONTACT_SECTION_RE.search(text)
    if contact_section is not None:
        text = text[: contact_section.start()]
    text = _EMAIL_RE.sub("[contact removed]", text)
    text = _PHONE_RE.sub("[contact removed]", text)
    return " ".join(text.split())[:MAX_PUBLIC_DESCRIPTION_CHARS]


def _dedupe_opportunities(rows: list[Opportunity]) -> list[Opportunity]:
    by_id: dict[str, Opportunity] = {}
    for row in rows:
        by_id.setdefault(row.native_source_id, row)
    return list(by_id.values())
