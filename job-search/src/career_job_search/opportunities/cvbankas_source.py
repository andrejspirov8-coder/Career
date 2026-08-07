"""Bounded CVBankas public-search opportunity adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)
from career_job_search.opportunities.sources.base import SourceDiscovery

DEFAULT_SEARCH_URL = "https://www.cvbankas.lt/"
DEFAULT_LOCATION_IDS = (606, 502)
DEFAULT_FETCH_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESULTS_PER_QUERY = 50
MAX_QUERIES = 6
ALLOWED_LOCATION_IDS = frozenset(DEFAULT_LOCATION_IDS)
MAX_SUMMARY_CHARS = 1200

_EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+370|00370|370)(?:[\s().-]*\d){8}(?!\d)",
)
_JOB_PATH_RE = re.compile(r"^/.+/1-(\d+)/?$")
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}
)


@dataclass
class CvBankasSourceDiscovery(SourceDiscovery):
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""


@dataclass(frozen=True)
class _SearchCard:
    url: str
    title: str
    company: str
    salary: str
    locations: tuple[str, ...]
    timing: str


class _SearchPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[_SearchCard] = []
        self.max_page = 1
        self._url = ""
        self._logo_alt = ""
        self._parts: dict[str, list[str]] = {}
        self._captures: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        name = tag.casefold()
        attributes = {key.casefold(): value or "" for key, value in attrs}
        self._record_page(attributes.get("href", ""))
        classes = set(attributes.get("class", "").casefold().split())

        if name == "a" and "list_a" in classes:
            self._start_card(attributes.get("href", ""))
            return
        if not self._url:
            return
        if name == "img" and not self._logo_alt:
            self._logo_alt = attributes.get("alt", "")

        inherited = self._captures[-1] if self._captures else ""
        capture = inherited
        if "list_h3" in classes:
            capture = "title"
        elif {"dib", "mt5", "mr5"}.issubset(classes):
            capture = "company"
        elif "salary_bl" in classes:
            capture = "salary"
        elif "list_city" in classes:
            self._parts.setdefault("location", []).append("\n")
            capture = "location"
        elif "txt_list_2" in classes:
            capture = "timing"
        if name not in _VOID_TAGS:
            self._captures.append(capture)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._url:
            return
        if tag.casefold() == "a":
            self._finish_card()
            return
        if self._captures:
            self._captures.pop()

    def handle_data(self, data: str) -> None:
        if not self._url or not self._captures:
            return
        capture = self._captures[-1]
        if capture:
            self._parts.setdefault(capture, []).append(data)

    def _start_card(self, url: str) -> None:
        if self._url:
            self._finish_card()
        self._url = url
        self._logo_alt = ""
        self._parts = {}
        self._captures = [""]

    def _finish_card(self) -> None:
        if not self._url:
            return
        location_text = "".join(self._parts.get("location", []))
        locations = tuple(
            text for line in location_text.splitlines() if (text := _normal_text(line))
        )
        self.cards.append(
            _SearchCard(
                url=self._url,
                title=_normal_text("".join(self._parts.get("title", []))),
                company=_normal_text(
                    "".join(self._parts.get("company", [])) or self._logo_alt
                ),
                salary=_normal_text("".join(self._parts.get("salary", []))),
                locations=locations,
                timing=_normal_text("".join(self._parts.get("timing", []))),
            )
        )
        self._url = ""
        self._logo_alt = ""
        self._parts = {}
        self._captures = []

    def _record_page(self, href: str) -> None:
        if not href:
            return
        parsed = urlsplit(href)
        host = parsed.netloc.casefold().removeprefix("www.")
        if host and host != "cvbankas.lt":
            return
        if parsed.path not in {"", "/"}:
            return
        for raw_page in parse_qs(parsed.query).get("page", []):
            try:
                page = int(raw_page)
            except (TypeError, ValueError):
                continue
            self.max_page = max(self.max_page, page)


def discover_cvbankas_public_search_source(
    config: dict[str, Any],
    *,
    fetcher: Callable[..., str],
    now: datetime | None = None,
) -> CvBankasSourceDiscovery:
    """Read one public first page per exact role phrase."""

    block = _source_cfg(config, "cvbankas_public_search")
    if not _enabled(block, default=False):
        return CvBankasSourceDiscovery()

    base_url = _validated_base_url(str(block.get("base_url") or DEFAULT_SEARCH_URL))
    timeout = _bounded_int(
        block.get("network_timeout_seconds", DEFAULT_FETCH_TIMEOUT_SECONDS),
        "network_timeout_seconds",
        maximum=120,
    )
    result_limit = _bounded_int(
        block.get(
            "max_results_per_query",
            DEFAULT_MAX_RESULTS_PER_QUERY,
        ),
        "max_results_per_query",
        maximum=DEFAULT_MAX_RESULTS_PER_QUERY,
    )
    max_queries = _bounded_int(
        block.get("max_queries", MAX_QUERIES),
        "max_queries",
        maximum=MAX_QUERIES,
    )
    location_ids = _configured_location_ids(
        block.get("location_ids", DEFAULT_LOCATION_IDS)
    )
    queries, query_list_capped = _configured_queries(
        block.get("queries"),
        max_queries=max_queries,
    )
    checked_at = _utc_datetime(now)

    by_id: dict[str, Opportunity] = {}
    failed_queries = 0
    paginated_queries = 0
    result_capped_queries = 0
    invalid_cards = 0
    successful_queries = 0
    for query in queries:
        try:
            page = fetcher(
                _search_url(
                    base_url,
                    query=query,
                    location_ids=location_ids,
                ),
                timeout=timeout,
            )
            max_page, cards = _search_results(page)
        except Exception:
            failed_queries += 1
            continue

        successful_queries += 1
        if max_page > 1:
            paginated_queries += 1
        if len(cards) > result_limit:
            result_capped_queries += 1
        for card in cards[:result_limit]:
            opportunity = _card_to_opportunity(card, checked_at=checked_at)
            if opportunity is None:
                invalid_cards += 1
                continue
            by_id.setdefault(opportunity.native_source_id, opportunity)

    if successful_queries == 0:
        raise RuntimeError("All CVBankas public search requests failed.")

    notes: list[str] = []
    if failed_queries:
        notes.append(
            f"{failed_queries} of {len(queries)} CVBankas searches failed; "
            "successful results were retained."
        )
    if paginated_queries:
        notes.append(
            f"{paginated_queries} CVBankas search(es) had additional pages; "
            "only the policy-bounded first page was retained."
        )
    if result_capped_queries:
        notes.append(
            f"{result_capped_queries} CVBankas search(es) exceeded the "
            f"{result_limit}-result cap."
        )
    if query_list_capped:
        notes.append(
            "The CVBankas query list exceeded its configured cap; "
            "only the bounded prefix was searched."
        )
    if invalid_cards:
        notes.append(
            f"{invalid_cards} invalid or out-of-scope CVBankas card(s) were ignored."
        )
    complete = not any(
        (
            failed_queries,
            paginated_queries,
            result_capped_queries,
            query_list_capped,
            invalid_cards,
        )
    )
    return CvBankasSourceDiscovery(
        opportunities=list(by_id.values()),
        complete=complete,
        note=" ".join(notes),
    )


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    if (
        parsed.scheme.casefold() != "https"
        or host != "cvbankas.lt"
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("CVBankas base_url must be https://www.cvbankas.lt/.")
    return "https://www.cvbankas.lt/"


def _configured_location_ids(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("CVBankas location_ids must be a list.")
    location_ids: list[int] = []
    for item in value:
        try:
            location_id = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("CVBankas location_ids must contain numeric IDs.") from exc
        if location_id not in ALLOWED_LOCATION_IDS:
            raise ValueError(
                "CVBankas location_ids may contain only Vilnius (606) "
                "and Darbas namuose (502)."
            )
        if location_id not in location_ids:
            location_ids.append(location_id)
    if not location_ids:
        raise ValueError("CVBankas location_ids cannot be empty.")
    return tuple(location_ids)


def _bounded_int(value: Any, name: str, *, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}.")
    return parsed


def _configured_queries(
    value: Any,
    *,
    max_queries: int,
) -> tuple[list[str], bool]:
    if not isinstance(value, list):
        raise ValueError("CVBankas queries must be a list.")
    queries: list[str] = []
    seen: set[str] = set()
    for item in value:
        query = _normal_text(item)
        if query.startswith('"') and query.endswith('"') and len(query) > 1:
            query = _normal_text(query[1:-1])
        if '"' in query:
            raise ValueError("CVBankas query phrases cannot contain double quotes.")
        key = query.casefold()
        if not query or key in seen:
            continue
        if len(query) > 100:
            raise ValueError("Each CVBankas query must be at most 100 characters.")
        seen.add(key)
        queries.append(query)
    if not queries:
        raise ValueError("At least one CVBankas query is required.")
    return queries[:max_queries], len(queries) > max_queries


def _utc_datetime(value: datetime | None) -> datetime:
    clock = value or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    return clock.astimezone(UTC)


def _search_url(
    base_url: str,
    *,
    query: str,
    location_ids: tuple[int, ...],
) -> str:
    parsed = urlsplit(base_url)
    query_string = urlencode(
        [
            ("keyw", f'"{query}"'),
            *(("location[]", str(location_id)) for location_id in location_ids),
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query_string, ""))


def _search_results(page: str) -> tuple[int, list[_SearchCard]]:
    if not isinstance(page, str):
        raise ValueError("CVBankas search response must be HTML.")
    parser = _SearchPageParser()
    parser.feed(page)
    parser.close()
    if parser._url:
        parser._finish_card()
    return parser.max_page, parser.cards


def _card_to_opportunity(
    card: _SearchCard,
    *,
    checked_at: datetime,
) -> Opportunity | None:
    native_id, source_url = _job_identity(card.url)
    title = _safe_public_text(card.title)
    company = _safe_public_text(card.company)
    location, remote_policy = _location(card.locations)
    if not native_id or not title or not company or not location:
        return None

    timing = _safe_public_text(card.timing)
    description = f"{title} at {company}. Location: {location}."
    if timing:
        description += f" Publisher timing: {timing}."
    checked_iso = checked_at.isoformat()
    return Opportunity(
        source="cvbankas",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=native_id,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        remote_policy=remote_policy,
        description=description[:MAX_SUMMARY_CHARS],
        salary_text=_safe_public_text(card.salary),
        live_status="live",
        live_checked_at=checked_iso,
        live_check_method="official_public_search",
        live_check_note="present_in_current_cvbankas_search",
        evidence=OpportunityEvidence(
            source_facts=["official_search:cvbankas"],
            company_facts=[company],
            role_facts=[title],
            location_facts=[location, remote_policy] if remote_policy else [location],
            risk_flags=["search_summary_only"],
            confidence=0.74,
        ),
    )


def _job_identity(value: str) -> tuple[str, str]:
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    match = _JOB_PATH_RE.fullmatch(parsed.path)
    if parsed.scheme.casefold() != "https" or host != "cvbankas.lt" or match is None:
        return "", ""
    source_url = urlunsplit(("https", "www.cvbankas.lt", parsed.path, "", ""))
    return match.group(1), source_url


def _location(values: tuple[str, ...]) -> tuple[str, str]:
    locations = [_safe_public_text(value) for value in values]
    locations = [value for value in locations if value]
    is_vilnius = any(value.casefold() == "vilniuje" for value in locations)
    is_remote = any(value.casefold() == "darbas namuose" for value in locations)
    if not is_vilnius and not is_remote:
        return "", ""
    normalized = [
        "Vilnius" if value.casefold() == "vilniuje" else value
        for value in locations
        if value.casefold() != "darbas namuose"
    ]
    if is_remote:
        normalized.append("Remote Lithuania")
    normalized = list(dict.fromkeys(normalized))
    return " / ".join(normalized), "Remote Lithuania" if is_remote else ""


def _normal_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _safe_public_text(value: Any) -> str:
    text = _normal_text(value)
    text = _EMAIL_RE.sub("[contact removed]", text)
    text = _PHONE_RE.sub("[contact removed]", text)
    return _normal_text(text)[:500]
