"""Official CV-Online public-search opportunity adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)

DEFAULT_CVONLINE_SEARCH_URL = "https://www.cvonline.lt/lt/search"
DEFAULT_FETCH_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESULTS_PER_QUERY = 200
MAX_PUBLIC_DESCRIPTION_CHARS = 6000
MAX_QUERIES = 6
SEARCH_TIMEZONE = ZoneInfo("Europe/Vilnius")

_EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+370|00370|370)(?:[\s().-]*\d){8}(?!\d)",
)
_CONTACT_SECTION_RE = re.compile(
    r"(?i)\b(?:kontaktinis\s+asmuo|contact\s+person|"
    r"jeigu\s+kyla\s+klausimų|kontaktai)\b",
)


@dataclass
class CvOnlineSourceDiscovery:
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""


def discover_cvonline_public_search_source(
    config: dict[str, Any],
    *,
    fetcher: Callable[..., str],
    now: datetime | None = None,
) -> CvOnlineSourceDiscovery:
    """Read bounded public CV-Online searches without opening listing pages."""

    block = _source_cfg(config, "cvonline_public_search")
    if not _enabled(block, default=False):
        return CvOnlineSourceDiscovery()

    base_url = _validated_base_url(
        str(block.get("base_url") or DEFAULT_CVONLINE_SEARCH_URL)
    )
    timeout = _positive_int(
        block.get("network_timeout_seconds", DEFAULT_FETCH_TIMEOUT_SECONDS),
        "network_timeout_seconds",
    )
    result_limit = _bounded_int(
        block.get("max_results_per_query", DEFAULT_MAX_RESULTS_PER_QUERY),
        "max_results_per_query",
        maximum=DEFAULT_MAX_RESULTS_PER_QUERY,
    )
    max_queries = _bounded_int(
        block.get("max_queries", MAX_QUERIES),
        "max_queries",
        maximum=MAX_QUERIES,
    )
    queries, query_list_capped = _configured_queries(
        block.get("queries"),
        max_queries=max_queries,
    )
    vilnius_town_id = str(block.get("vilnius_town_id") or "540")
    lithuania_country_id = str(block.get("lithuania_country_id") or "92")

    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    local_date = clock.astimezone(SEARCH_TIMEZONE).date()

    by_id: dict[str, Opportunity] = {}
    failed_queries = 0
    capped_queries = 0
    successful_queries = 0
    for query in queries:
        try:
            page = fetcher(
                _search_url(base_url, query=query, limit=result_limit),
                timeout=timeout,
            )
            total, rows = _search_results(page)
        except Exception:
            failed_queries += 1
            continue

        successful_queries += 1
        if total > result_limit:
            capped_queries += 1
        for row in rows:
            opportunity = _row_to_opportunity(
                row,
                local_date=local_date,
                checked_at=clock,
                vilnius_town_id=vilnius_town_id,
                lithuania_country_id=lithuania_country_id,
            )
            if opportunity is not None:
                by_id.setdefault(opportunity.native_source_id, opportunity)

    if successful_queries == 0:
        raise RuntimeError("All CV-Online public search requests failed.")

    notes: list[str] = []
    if failed_queries:
        notes.append(
            f"{failed_queries} of {len(queries)} CV-Online searches failed; "
            "successful results were retained."
        )
    if capped_queries:
        notes.append(
            f"{capped_queries} CV-Online searches exceeded the "
            f"{result_limit}-result cap."
        )
    if query_list_capped:
        notes.append(
            "The CV-Online query list exceeded its configured cap; "
            "only the bounded prefix was searched."
        )
    return CvOnlineSourceDiscovery(
        opportunities=list(by_id.values()),
        complete=not (failed_queries or capped_queries or query_list_capped),
        note=" ".join(notes),
    )


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _validated_base_url(value: str) -> str:
    raw = value.strip()
    parsed = urlsplit(raw)
    host = parsed.netloc.casefold().removeprefix("www.")
    if parsed.scheme.casefold() != "https" or host != "cvonline.lt":
        raise ValueError("CV-Online base_url must use https://www.cvonline.lt.")
    if not parsed.path:
        raise ValueError("CV-Online base_url must include a search path.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _positive_int(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return parsed


def _bounded_int(value: Any, name: str, *, maximum: int) -> int:
    parsed = _positive_int(value, name)
    if parsed > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}.")
    return parsed


def _configured_queries(
    value: Any,
    *,
    max_queries: int,
) -> tuple[list[str], bool]:
    if not isinstance(value, list):
        raise ValueError("CV-Online queries must be a list.")
    queries: list[str] = []
    seen: set[str] = set()
    for item in value:
        query = " ".join(str(item or "").split())
        key = query.casefold()
        if not query or key in seen:
            continue
        if len(query) > 100:
            raise ValueError("Each CV-Online query must be at most 100 characters.")
        seen.add(key)
        queries.append(query)
    if not queries:
        raise ValueError("At least one CV-Online query is required.")
    return queries[:max_queries], len(queries) > max_queries


def _search_url(base_url: str, *, query: str, limit: int) -> str:
    parsed = urlsplit(base_url)
    encoded = urlencode(
        [
            ("limit", str(limit)),
            ("offset", "0"),
            ("keywords[0]", query),
            ("locations[0]", "Vilnius"),
            ("fuzzy", "false"),
            ("isHourlySalary", "false"),
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, encoded, ""))


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capturing = False
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "script":
            return
        attributes = {key.casefold(): value for key, value in attrs}
        self._capturing = attributes.get("id") == "__NEXT_DATA__"

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script":
            self._capturing = False


def _search_results(page: str) -> tuple[int, list[dict[str, Any]]]:
    parser = _NextDataParser()
    parser.feed(page)
    raw = "".join(parser.parts).strip()
    if not raw:
        raise ValueError("CV-Online search page is missing __NEXT_DATA__.")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("CV-Online search page data must be an object.")
    page_props = (payload.get("props") or {}).get("pageProps") or {}
    search_results = page_props.get("searchResults") or {}
    if not isinstance(search_results, dict):
        raise ValueError("CV-Online search results are malformed.")
    vacancies = search_results.get("vacancies")
    if not isinstance(vacancies, list):
        raise ValueError("CV-Online search results are missing vacancies.")
    rows = [row for row in vacancies if isinstance(row, dict)]
    try:
        total = int(search_results.get("total"))
    except (TypeError, ValueError):
        total = len(rows)
    return max(total, len(rows)), rows


def _row_to_opportunity(
    row: dict[str, Any],
    *,
    local_date: date,
    checked_at: datetime,
    vilnius_town_id: str,
    lithuania_country_id: str,
) -> Opportunity | None:
    native_id = str(row.get("id") or "").strip()
    title = " ".join(str(row.get("positionTitle") or "").split())
    company = " ".join(str(row.get("employerName") or "").split())
    town_id = str(row.get("townId") or "")
    country_id = str(row.get("countryId") or "")
    remote_type = str(row.get("remoteWorkType") or "").strip().upper()
    is_vilnius = town_id == vilnius_town_id
    is_remote_lithuania = (
        country_id == lithuania_country_id and remote_type == "FULLY_REMOTE"
    )
    if not native_id or not title or not company:
        return None
    if not is_vilnius and not is_remote_lithuania:
        return None

    deadline, deadline_date = _deadline(row.get("expirationDate"))
    if deadline_date is not None and deadline_date < local_date:
        return None

    location = "Vilnius" if is_vilnius else "Lithuania"
    remote_policy = _remote_policy(remote_type, is_vilnius=is_vilnius)
    description = _safe_public_job_text(str(row.get("positionContent") or ""))
    if not description:
        description = f"{title} at {company}."
    updated = str(row.get("renewedDate") or row.get("publishDate") or "").strip()
    checked_iso = checked_at.astimezone(UTC).isoformat()
    return Opportunity(
        source="cvonline",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=native_id,
        source_url=f"https://www.cvonline.lt/lt/vacancy/{native_id}",
        title=title,
        company=company,
        location=location,
        remote_policy=remote_policy,
        description=description,
        salary_text=_salary_text(row),
        deadline=deadline,
        source_updated_at=updated,
        live_status="live",
        live_checked_at=checked_iso,
        live_check_method="official_public_search",
        live_check_note="present_in_current_cvonline_search",
        evidence=OpportunityEvidence(
            source_facts=["official_search:cvonline"],
            company_facts=[company],
            role_facts=[title],
            location_facts=[location, remote_policy],
            risk_flags=["search_summary_only"],
            confidence=0.82,
        ),
    )


def _remote_policy(remote_type: str, *, is_vilnius: bool) -> str:
    if remote_type == "FULLY_REMOTE":
        return "Remote Lithuania"
    if remote_type == "HYBRID" and is_vilnius:
        return "Hybrid in Vilnius"
    return "Onsite in Vilnius"


def _deadline(value: Any) -> tuple[str, date | None]:
    text = str(value or "").strip()
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if match is None:
        return "", None
    deadline = match.group(1)
    try:
        return deadline, date.fromisoformat(deadline)
    except ValueError:
        return "", None


def _salary_text(row: dict[str, Any]) -> str:
    lower = _number_text(row.get("salaryFrom"))
    upper = _number_text(row.get("salaryTo"))
    if lower and upper and lower != upper:
        amount = f"{lower}–{upper}"
    else:
        amount = lower or upper
    if not amount:
        return ""
    period = "hour" if bool(row.get("hourlySalary")) else "month"
    return f"{amount} EUR gross/{period}"


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


def _safe_public_job_text(value: str) -> str:
    parser = _PublicTextParser()
    parser.feed(value)
    text = " ".join("".join(parser.parts).split())
    contact_section = _CONTACT_SECTION_RE.search(text)
    if contact_section is not None:
        text = text[: contact_section.start()]
    text = _EMAIL_RE.sub("[contact removed]", text)
    text = _PHONE_RE.sub("[contact removed]", text)
    return " ".join(text.split())[:MAX_PUBLIC_DESCRIPTION_CHARS]
