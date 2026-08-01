"""Official CVMarket RSS opportunity adapter."""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit
from xml.etree.ElementTree import XMLParser

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)
from career_job_search.opportunities.normalization import infer_remote_policy

DEFAULT_FETCH_TIMEOUT_SECONDS = 20
DEFAULT_CVMARKET_RSS_URL = "https://www.cvmarket.lt/rss-listings.xml"

_COMPANY_ACRONYMS = {
    "ab": "AB",
    "as": "AS",
    "ey": "EY",
    "iki": "IKI",
    "lt": "LT",
    "ltg": "LTG",
    "mb": "MB",
    "se": "SE",
    "uab": "UAB",
    "vsi": "VŠĮ",
}


@dataclass
class CvMarketSourceDiscovery:
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""


def discover_cvmarket_rss_source(
    config: dict[str, Any],
    *,
    fetcher: Callable[..., str],
    now: datetime | None = None,
) -> CvMarketSourceDiscovery:
    """Read the official CVMarket RSS feed without scraping listing pages."""

    block = _source_cfg(config, "cvmarket_rss")
    if not _enabled(block, default=False):
        return CvMarketSourceDiscovery()

    timeout = int(block.get("network_timeout_seconds") or DEFAULT_FETCH_TIMEOUT_SECONDS)
    feed_url = str(block.get("feed_url") or DEFAULT_CVMARKET_RSS_URL).strip()
    parser = XMLParser(target=ElementTree.TreeBuilder())  # noqa: S314  # stdlib parser; DTD/entities disabled by default
    root = ElementTree.fromstring(fetcher(feed_url, timeout=timeout), parser=parser)  # noqa: S314  # feed URL from trusted config
    channel = root.find("channel")
    if channel is None:
        raise ValueError("CVMarket RSS feed is missing its channel.")

    allowed_locations = {
        _slugify(str(value))
        for value in block.get("locations", ["vilnius"])
        if str(value).strip()
    }
    opportunities: list[Opportunity] = []
    for item in channel.findall("item"):
        opportunity = _item_to_opportunity(
            item,
            allowed_locations=allowed_locations,
        )
        if opportunity is not None:
            opportunities.append(opportunity)

    max_items = _non_negative_int(block.get("max_items"), "max_items")
    complete = not max_items or len(opportunities) <= max_items
    if max_items:
        opportunities = opportunities[:max_items]

    feed_updated = _parse_rss_datetime(channel.findtext("lastBuildDate") or "")
    max_age_hours = max(1, int(block.get("max_feed_age_hours") or 48))
    status, note = _feed_freshness(
        feed_updated,
        now=now,
        max_age_hours=max_age_hours,
    )
    return CvMarketSourceDiscovery(
        opportunities=opportunities,
        complete=complete,
        status=status,
        note=note,
    )


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _item_to_opportunity(
    item: ElementTree.Element,
    *,
    allowed_locations: set[str],
) -> Opportunity | None:
    title = " ".join((item.findtext("title") or "").split())
    link = (item.findtext("link") or "").strip()
    parsed_url = urlsplit(link)
    host = parsed_url.netloc.casefold().removeprefix("www.")
    path = parsed_url.path.strip("/")
    id_match = re.search(r"-(\d+)$", path)
    if (
        not title
        or host != "cvmarket.lt"
        or parsed_url.scheme.casefold() != "https"
        or id_match is None
    ):
        return None

    native_id = id_match.group(1)
    listing_slug = path[: id_match.start()]
    title_slug = _slugify(title)
    remainder = (
        listing_slug.removeprefix(f"{title_slug}-")
        if listing_slug.startswith(f"{title_slug}-")
        else listing_slug
    )
    location, company_slug = _location_company(
        remainder,
        allowed_locations=allowed_locations,
    )
    if not location or not company_slug:
        return None

    company = _company_from_slug(company_slug)
    published = _parse_rss_datetime(item.findtext("pubDate") or "")
    source_updated_at = published.isoformat() if published else ""
    return Opportunity(
        source="cvmarket",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=native_id,
        source_url=link,
        title=title,
        company=company,
        location=location,
        remote_policy=infer_remote_policy(f"{title} {location} {listing_slug}"),
        description=(
            f"{title}. Summary imported from CVMarket's official public RSS feed."
        ),
        source_updated_at=source_updated_at,
        live_status="unverified",
        live_check_method="official_rss",
        live_check_note="rss_summary_requires_listing_verification",
        evidence=OpportunityEvidence(
            source_facts=["official_rss:cvmarket"],
            company_facts=[company],
            role_facts=[title],
            location_facts=[location],
            risk_flags=["rss_summary_only", "needs_live_verification"],
            confidence=0.6,
        ),
    )


def _location_company(
    remainder: str,
    *,
    allowed_locations: set[str],
) -> tuple[str, str]:
    if "vilnius" in allowed_locations:
        for prefix in ("vilnius-", "vilniuje-", "vilniaus-"):
            if remainder.startswith(prefix):
                return "Vilnius", remainder.removeprefix(prefix)
    return "", ""


def _company_from_slug(value: str) -> str:
    return " ".join(
        _COMPANY_ACRONYMS.get(part, part.capitalize())
        for part in value.split("-")
        if part
    )


def _feed_freshness(
    updated_at: datetime | None,
    *,
    now: datetime | None,
    max_age_hours: int,
) -> tuple[str | None, str]:
    if updated_at is None:
        return "stale", "CVMarket RSS did not provide a usable update time."
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    age_hours = max(
        0,
        int(
            (clock.astimezone(UTC) - updated_at.astimezone(UTC)).total_seconds() // 3600
        ),
    )
    if age_hours > max_age_hours:
        return (
            "stale",
            f"CVMarket RSS is {age_hours} hours old; verify listings before use.",
        )
    return None, ""


def _parse_rss_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")


def _non_negative_int(value: Any, name: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer.") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return parsed
