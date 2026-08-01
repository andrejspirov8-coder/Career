"""Official Work in Lithuania public job-search adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)

DEFAULT_API_URL = "https://jobs.workinlithuania.com/api/job-offers"
DEFAULT_CITY_IDS = (2, 14)
DEFAULT_FETCH_TIMEOUT_SECONDS = 20
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_RECORDS = 100
MAX_ALLOWED_PAGES = 10
MAX_ALLOWED_RECORDS = 200
ALLOWED_CITY_IDS = frozenset(DEFAULT_CITY_IDS)
MAX_SUMMARY_CHARS = 1800

_EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+370|00370|370)(?:[\s().-]*\d){8}(?!\d)",
)
_JOB_PATH_RE = re.compile(r"^/job-offers/(\d+)(?:-[^/]*)?/?$")


@dataclass
class WorkInLithuaniaSourceDiscovery:
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""


@dataclass(frozen=True)
class _Page:
    rows: list[dict[str, Any]]
    current_page: int
    last_page: int
    total: int


def discover_workinlithuania_public_search_source(
    config: dict[str, Any],
    *,
    fetcher: Callable[..., Any],
    now: datetime | None = None,
) -> WorkInLithuaniaSourceDiscovery:
    """Read the complete bounded Vilnius/remote publisher search."""

    block = _source_cfg(config, "workinlithuania_public_search")
    if not _enabled(block, default=False):
        return WorkInLithuaniaSourceDiscovery()

    api_url = _validated_api_url(str(block.get("api_url") or DEFAULT_API_URL))
    city_ids = _configured_city_ids(block.get("city_ids", DEFAULT_CITY_IDS))
    timeout = _bounded_int(
        block.get("network_timeout_seconds", DEFAULT_FETCH_TIMEOUT_SECONDS),
        "network_timeout_seconds",
        maximum=120,
    )
    max_pages = _bounded_int(
        block.get("max_pages", DEFAULT_MAX_PAGES),
        "max_pages",
        maximum=MAX_ALLOWED_PAGES,
    )
    max_records = _bounded_int(
        block.get("max_records", DEFAULT_MAX_RECORDS),
        "max_records",
        maximum=MAX_ALLOWED_RECORDS,
    )
    checked_at = _utc_datetime(now)

    try:
        first = _page_payload(
            fetcher(
                _page_url(api_url, city_ids=city_ids, page=1),
                timeout=timeout,
            ),
            expected_page=1,
        )
    except Exception as exc:
        raise RuntimeError(
            "Work in Lithuania public search could not be read."
        ) from exc

    pages_to_read = min(first.last_page, max_pages)
    fetched_pages: list[_Page] = [first]
    failed_pages = 0
    metadata_changed = False
    for page_number in range(2, pages_to_read + 1):
        try:
            page = _page_payload(
                fetcher(
                    _page_url(api_url, city_ids=city_ids, page=page_number),
                    timeout=timeout,
                ),
                expected_page=page_number,
            )
        except Exception:
            failed_pages += 1
            continue
        if page.last_page != first.last_page or page.total != first.total:
            metadata_changed = True
        fetched_pages.append(page)

    opportunities: list[Opportunity] = []
    seen_ids: set[str] = set()
    duplicate_rows = 0
    invalid_rows = 0
    record_cap_reached = False
    for page in fetched_pages:
        for row in page.rows:
            native_id = str(row.get("id") or "").strip()
            if not native_id or native_id in seen_ids:
                duplicate_rows += 1
                continue
            seen_ids.add(native_id)
            if len(seen_ids) > max_records:
                record_cap_reached = True
                break
            opportunity = _row_to_opportunity(row, checked_at=checked_at)
            if opportunity is None:
                invalid_rows += 1
                continue
            opportunities.append(opportunity)
        if record_cap_reached:
            break

    page_cap_reached = first.last_page > max_pages
    total_cap_reached = first.total > max_records
    missing_rows = (
        not page_cap_reached
        and not total_cap_reached
        and not failed_pages
        and len(seen_ids) != first.total
    )
    complete = not any(
        (
            page_cap_reached,
            total_cap_reached,
            record_cap_reached,
            failed_pages,
            metadata_changed,
            duplicate_rows,
            invalid_rows,
            missing_rows,
        )
    )
    notes: list[str] = []
    if failed_pages:
        notes.append(
            f"{failed_pages} Work in Lithuania result page(s) failed; "
            "successful pages were retained."
        )
    if page_cap_reached:
        notes.append(f"The Work in Lithuania search exceeded the {max_pages}-page cap.")
    if total_cap_reached or record_cap_reached:
        notes.append(
            f"The Work in Lithuania search exceeded the {max_records}-record cap."
        )
    if metadata_changed:
        notes.append("Work in Lithuania result totals changed during pagination.")
    if duplicate_rows:
        notes.append(
            f"{duplicate_rows} duplicate Work in Lithuania result row(s) were ignored."
        )
    if invalid_rows:
        notes.append(
            f"{invalid_rows} invalid or out-of-scope Work in Lithuania row(s) "
            "were ignored."
        )
    if missing_rows:
        notes.append(
            "The Work in Lithuania result count did not match the publisher total."
        )
    return WorkInLithuaniaSourceDiscovery(
        opportunities=opportunities,
        complete=complete,
        note=" ".join(notes),
    )


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _validated_api_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    path = parsed.path.rstrip("/")
    if (
        parsed.scheme.casefold() != "https"
        or host != "jobs.workinlithuania.com"
        or path != "/api/job-offers"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Work in Lithuania api_url must be "
            "https://jobs.workinlithuania.com/api/job-offers."
        )
    return urlunsplit(("https", "jobs.workinlithuania.com", path, "", ""))


def _configured_city_ids(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("Work in Lithuania city_ids must be a list.")
    city_ids: list[int] = []
    for item in value:
        try:
            city_id = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Work in Lithuania city_ids must contain numeric IDs."
            ) from exc
        if city_id not in ALLOWED_CITY_IDS:
            raise ValueError(
                "Work in Lithuania city_ids may contain only Vilnius (2) "
                "and Remote job (14)."
            )
        if city_id not in city_ids:
            city_ids.append(city_id)
    if not city_ids:
        raise ValueError("Work in Lithuania city_ids cannot be empty.")
    return tuple(city_ids)


def _bounded_int(value: Any, name: str, *, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}.")
    return parsed


def _utc_datetime(value: datetime | None) -> datetime:
    clock = value or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    return clock.astimezone(UTC)


def _page_url(api_url: str, *, city_ids: tuple[int, ...], page: int) -> str:
    parsed = urlsplit(api_url)
    query = urlencode(
        [
            ("filter[cities]", ",".join(str(city_id) for city_id in city_ids)),
            ("page", str(page)),
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _page_payload(payload: Any, *, expected_page: int) -> _Page:
    if not isinstance(payload, dict):
        raise ValueError("Work in Lithuania response must be an object.")
    raw_rows = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(raw_rows, list) or not isinstance(meta, dict):
        raise ValueError("Work in Lithuania response is missing data or meta.")
    current_page = _metadata_int(meta.get("current_page"), "current_page")
    last_page = _metadata_int(meta.get("last_page"), "last_page")
    total = _metadata_int(meta.get("total"), "total", allow_zero=True)
    if current_page != expected_page or last_page < current_page:
        raise ValueError("Work in Lithuania pagination metadata is inconsistent.")
    rows = [row for row in raw_rows if isinstance(row, dict)]
    if len(rows) != len(raw_rows):
        raise ValueError("Work in Lithuania result rows must be objects.")
    return _Page(
        rows=rows,
        current_page=current_page,
        last_page=last_page,
        total=total,
    )


def _metadata_int(value: Any, name: str, *, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Work in Lithuania {name} must be numeric.") from exc
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValueError(f"Work in Lithuania {name} is out of range.")
    return parsed


def _row_to_opportunity(
    row: dict[str, Any],
    *,
    checked_at: datetime,
) -> Opportunity | None:
    native_id = str(row.get("id") or "").strip()
    if not native_id.isdigit() or int(native_id) < 1:
        return None
    title = _safe_public_text(row.get("name"))
    company_payload = row.get("company")
    company = _safe_public_text(
        company_payload.get("name") if isinstance(company_payload, dict) else ""
    )
    location = _safe_public_text(row.get("location"))
    if not title or not company or not _is_target_location(location):
        return None
    source_url = _validated_job_url(str(row.get("slug") or ""), native_id=native_id)
    if not source_url:
        return None

    seniority = _safe_public_text(row.get("seniority"))
    skills = _safe_string_list(row.get("skills"), maximum=12)
    added_at = _safe_public_text(row.get("added_at"))
    expires = _safe_public_text(row.get("expire_at"))
    summary_parts = [f"{title} at {company}.", f"Location: {location}."]
    if seniority:
        summary_parts.append(f"Seniority: {seniority}.")
    if skills:
        summary_parts.append(f"Skills: {', '.join(skills)}.")
    if added_at:
        summary_parts.append(f"Publisher timing: {added_at}.")
    if expires:
        summary_parts.append(f"Availability: {expires}.")
    description = " ".join(summary_parts)[:MAX_SUMMARY_CHARS]
    remote_policy = "Remote Lithuania" if "remote job" in location.casefold() else ""
    checked_iso = checked_at.isoformat()
    role_facts = [title, seniority, *skills]
    return Opportunity(
        source="workinlithuania",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=native_id,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        remote_policy=remote_policy,
        description=description,
        salary_text=_salary_text(row.get("salary")),
        live_status="live",
        live_checked_at=checked_iso,
        live_check_method="official_public_api",
        live_check_note="present_in_current_workinlithuania_search",
        evidence=OpportunityEvidence(
            source_facts=["official_api:workinlithuania"],
            company_facts=[company],
            role_facts=[fact for fact in role_facts if fact],
            location_facts=[location, remote_policy] if remote_policy else [location],
            risk_flags=["search_summary_only"],
            confidence=0.86,
        ),
    )


def _validated_job_url(value: str, *, native_id: str) -> str:
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    match = _JOB_PATH_RE.fullmatch(parsed.path)
    if (
        parsed.scheme.casefold() != "https"
        or host != "jobs.workinlithuania.com"
        or match is None
        or match.group(1) != native_id
    ):
        return ""
    return urlunsplit(("https", "jobs.workinlithuania.com", parsed.path, "", ""))


def _is_target_location(location: str) -> bool:
    value = location.casefold()
    return "vilnius" in value or "remote job" in value


def _safe_string_list(value: Any, *, maximum: int) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = _safe_public_text(item)
        if text and text.casefold() not in {row.casefold() for row in rows}:
            rows.append(text)
        if len(rows) >= maximum:
            break
    return rows


def _safe_public_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    text = _EMAIL_RE.sub("[contact removed]", text)
    text = _PHONE_RE.sub("[contact removed]", text)
    return " ".join(text.split())[:500]


def _salary_text(value: Any) -> str:
    salary = _safe_public_text(value)
    if not salary:
        return ""
    return f"{salary} EUR (publisher period not stated)"
