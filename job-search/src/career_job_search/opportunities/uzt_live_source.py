"""Bounded fallback for the official UŽT public vacancy search."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)

DEFAULT_UZT_LIVE_SEARCH_URL = "https://uzt.lt/laisvos-darbo-vietos/436/results"
DEFAULT_UZT_MUNICIPALITY_ID = 461
LIVE_PAGE_SIZE = 100
DEFAULT_LIVE_RESULT_LIMIT = 500
MAX_LIVE_RESULT_LIMIT = 500
MAX_LIVE_AREA_IDS = 12
MAX_SUMMARY_CHARS = 1200

_DETAIL_PATH_RE = re.compile(
    r"^/laisvos-darbo-vietos/436(?:/p\d+)?/skelbimas/(DV-[A-Z0-9-]+)$",
)
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+370|00370|370)(?:[\s().-]*\d){8}(?!\d)",
)
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}
)


@dataclass
class UztLiveSourceDiscovery:
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
    district: str
    location: str
    created_date: str
    expiry_date: str


class _SearchPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[_SearchCard] = []
        self.has_next_page = False
        self._url = ""
        self._parts: dict[str, list[str]] = {}
        self._captures: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        name = tag.casefold()
        attributes = {key.casefold(): value or "" for key, value in attrs}
        rel = set(attributes.get("rel", "").casefold().split())
        if name == "link" and "next" in rel:
            self.has_next_page = True

        classes = set(attributes.get("class", "").casefold().split())
        if name == "a" and "list__item" in classes:
            self._start_card(attributes.get("href", ""))
            return
        if not self._url:
            return

        inherited = self._captures[-1] if self._captures else ""
        capture = inherited
        for class_name, field_name in (
            ("title", "title"),
            ("company", "company"),
            ("salary", "salary"),
            ("district", "district"),
            ("location", "location"),
            ("created-date", "created_date"),
            ("expiry-date", "expiry_date"),
        ):
            if class_name in classes:
                capture = field_name
                break
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
        self._parts = {}
        self._captures = [""]

    def _finish_card(self) -> None:
        if not self._url:
            return
        self.cards.append(
            _SearchCard(
                url=self._url,
                title=_joined(self._parts, "title"),
                company=_joined(self._parts, "company"),
                salary=_joined(self._parts, "salary"),
                district=_joined(self._parts, "district"),
                location=_joined(self._parts, "location"),
                created_date=_joined(self._parts, "created_date"),
                expiry_date=_joined(self._parts, "expiry_date"),
            )
        )
        self._url = ""
        self._parts = {}
        self._captures = []


def discover_uzt_live_search_source(
    block: dict[str, Any],
    *,
    fetcher: Callable[..., str],
    now: datetime | None = None,
) -> UztLiveSourceDiscovery:
    """Read one newest-first page without opening vacancy contact sections."""

    base_url = _validated_search_url(
        str(block.get("live_fallback_url") or DEFAULT_UZT_LIVE_SEARCH_URL)
    )
    municipality_id = _bounded_positive_int(
        block.get(
            "live_fallback_municipality_id",
            DEFAULT_UZT_MUNICIPALITY_ID,
        ),
        "live_fallback_municipality_id",
        maximum=10_000,
    )
    max_records = _bounded_positive_int(
        block.get("live_fallback_max_records", DEFAULT_LIVE_RESULT_LIMIT),
        "live_fallback_max_records",
        maximum=MAX_LIVE_RESULT_LIMIT,
    )
    area_ids = _configured_ids(
        block.get("live_fallback_area_ids"),
        "live_fallback_area_ids",
        maximum_items=MAX_LIVE_AREA_IDS,
    )
    timeout = _bounded_positive_int(
        block.get("network_timeout_seconds", 20),
        "network_timeout_seconds",
        maximum=120,
    )
    checked_at = _utc_datetime(now)
    cards: list[_SearchCard] = []
    has_next_page = True
    pagination_failed = False
    offset = 0
    while has_next_page and offset < max_records:
        try:
            page = fetcher(
                _search_url(
                    base_url,
                    municipality_id=municipality_id,
                    area_ids=area_ids,
                    offset=offset,
                ),
                timeout=timeout,
            )
        except Exception:
            if not cards:
                raise
            pagination_failed = True
            break
        parser = _parse_search_page(page)
        if not parser.cards:
            if not cards:
                raise RuntimeError("Official UŽT search returned no vacancy summaries.")
            pagination_failed = True
            break
        cards.extend(parser.cards)
        has_next_page = parser.has_next_page
        offset += LIVE_PAGE_SIZE

    opportunities: list[Opportunity] = []
    invalid_cards = 0
    seen_ids: set[str] = set()
    for card in cards[:max_records]:
        opportunity = _card_to_opportunity(card, checked_at=checked_at)
        if opportunity is None:
            invalid_cards += 1
            continue
        if opportunity.native_source_id in seen_ids:
            continue
        seen_ids.add(opportunity.native_source_id)
        opportunities.append(opportunity)
    if not opportunities:
        raise RuntimeError("Official UŽT search returned no valid vacancy summaries.")

    latest_update = _latest_date(
        opportunity.source_updated_at for opportunity in opportunities
    )
    max_age_days = max(1, int(block.get("max_feed_age_days") or 3))
    status, freshness_note = _feed_freshness(
        latest_update,
        now=checked_at,
        max_age_hours=max_age_days * 24,
    )
    complete = not any(
        (
            has_next_page,
            len(cards) > max_records,
            invalid_cards,
            pagination_failed,
        )
    )
    notes = [freshness_note] if freshness_note else []
    if not complete:
        notes.append(
            "Official live UŽT search is capped; "
            f"imported {len(opportunities)} newest valid summaries."
        )
    return UztLiveSourceDiscovery(
        opportunities=opportunities,
        complete=complete,
        status=status,
        note=" ".join(notes),
    )


def _parse_search_page(page: str) -> _SearchPageParser:
    if not isinstance(page, str):
        raise ValueError("Official UŽT search response must be HTML.")
    parser = _SearchPageParser()
    parser.feed(page)
    parser.close()
    if parser._url:
        parser._finish_card()
    return parser


def _card_to_opportunity(
    card: _SearchCard,
    *,
    checked_at: datetime,
) -> Opportunity | None:
    native_id, source_url = _job_identity(card.url)
    title = _safe_public_text(card.title)
    company = _safe_public_text(card.company)
    location = _location_text(card.location, card.district)
    created_date = _date_text(card.created_date)
    expiry_date = _date_text(card.expiry_date)
    if not all((native_id, title, company, location, created_date)):
        return None

    checked_iso = checked_at.isoformat()
    description = (
        f"{title} at {company}. Location: {location}. "
        "Summary from the current official UŽT public vacancy search."
    )
    return Opportunity(
        source="uzt_open_data",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=native_id,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        description=description[:MAX_SUMMARY_CHARS],
        salary_text=_safe_public_text(card.salary),
        deadline=expiry_date,
        source_updated_at=created_date,
        live_status="live",
        live_checked_at=checked_iso,
        live_check_method="official_public_search",
        live_check_note="present_in_current_uzt_search",
        evidence=OpportunityEvidence(
            source_facts=["official_search:uzt"],
            company_facts=[company],
            role_facts=[title],
            location_facts=[location],
            risk_flags=["search_summary_only"],
            confidence=0.78,
        ),
    )


def _validated_search_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    if (
        parsed.scheme.casefold() != "https"
        or host != "uzt.lt"
        or parsed.path != "/laisvos-darbo-vietos/436/results"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "UŽT live_fallback_url must be the official HTTPS vacancy search URL."
        )
    return DEFAULT_UZT_LIVE_SEARCH_URL


def _search_url(
    base_url: str,
    *,
    municipality_id: int,
    area_ids: tuple[int, ...],
    offset: int,
) -> str:
    parsed = urlsplit(base_url)
    path = parsed.path if offset == 0 else f"{parsed.path}/p{offset}"
    query = urlencode(
        [
            ("n", str(LIVE_PAGE_SIZE)),
            ("o", "ctime"),
            ("m[]", str(municipality_id)),
            *(("a[]", str(area_id)) for area_id in area_ids),
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


def _job_identity(value: str) -> tuple[str, str]:
    absolute = urljoin(DEFAULT_UZT_LIVE_SEARCH_URL, value.strip())
    parsed = urlsplit(absolute)
    host = parsed.netloc.casefold().removeprefix("www.")
    match = _DETAIL_PATH_RE.fullmatch(parsed.path)
    if parsed.scheme.casefold() != "https" or host != "uzt.lt" or match is None:
        return "", ""
    source_path = f"/laisvos-darbo-vietos/436/skelbimas/{match.group(1)}"
    source_url = urlunsplit(("https", "uzt.lt", source_path, "", ""))
    return match.group(1), source_url


def _joined(parts: dict[str, list[str]], name: str) -> str:
    return " ".join("".join(parts.get(name, [])).split())


def _safe_public_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    text = _EMAIL_RE.sub("[contact removed]", text)
    text = _PHONE_RE.sub("[contact removed]", text)
    return " ".join(text.split())


def _location_text(location: str, district: str) -> str:
    safe_location = _safe_public_text(location)
    safe_district = _safe_public_text(district)
    combined = f"{safe_location} {safe_district}".casefold()
    if "vilnius" in combined or "vilniaus miesto sav" in combined:
        return "Vilnius"
    return safe_location or safe_district


def _date_text(value: str) -> str:
    match = _ISO_DATE_RE.search(value)
    if not match:
        return ""
    try:
        return datetime.fromisoformat(match.group(1)).date().isoformat()
    except ValueError:
        return ""


def _latest_date(values: Any) -> datetime | None:
    parsed: list[datetime] = []
    for value in values:
        try:
            parsed.append(datetime.fromisoformat(str(value)).replace(tzinfo=UTC))
        except ValueError:
            continue
    return max(parsed, default=None)


def _feed_freshness(
    updated_at: datetime | None,
    *,
    now: datetime,
    max_age_hours: int,
) -> tuple[str | None, str]:
    if updated_at is None:
        return "stale", "Official UŽT search did not provide a usable update time."
    age_hours = max(
        0,
        int((now - updated_at.astimezone(UTC)).total_seconds() // 3600),
    )
    if age_hours > max_age_hours:
        return (
            "stale",
            f"Official UŽT search is {age_hours} hours old.",
        )
    return None, ""


def _utc_datetime(value: datetime | None) -> datetime:
    clock = value or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    return clock.astimezone(UTC)


def _bounded_positive_int(value: Any, name: str, *, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}.")
    return parsed


def _configured_ids(
    value: Any,
    name: str,
    *,
    maximum_items: int,
) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError(f"{name} must be a list.")
    values: list[int] = []
    for item in value:
        parsed = _bounded_positive_int(item, name, maximum=10_000)
        if parsed not in values:
            values.append(parsed)
    if len(values) > maximum_items:
        raise ValueError(f"{name} may contain at most {maximum_items} values.")
    return tuple(values)
